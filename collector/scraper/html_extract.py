from __future__ import annotations

import html
import json
import re
from collections.abc import Sequence
from typing import Any
from urllib.parse import urljoin

from scrapy import Selector


def normalize_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def selector_text(selector: Selector | None) -> str:
    if selector is None:
        return ""
    return normalize_whitespace(" ".join(part for part in selector.xpath(".//text()").getall() if part))


def strip_tags(source: str) -> str:
    selector = Selector(text=source or "")
    parts = selector.xpath("//body//text()[not(ancestor::script) and not(ancestor::style)] | //text()[not(ancestor::script) and not(ancestor::style) and not(ancestor::head)]").getall()
    return normalize_whitespace(html.unescape(" ".join(parts)))


def extract_tag_text(selector: Selector, tag: str) -> str:
    return normalize_whitespace(" ".join(selector.css(f"{tag} ::text").getall()))


def extract_meta_content(selector: Selector, attr_name: str, attr_value: str) -> str:
    for meta in selector.css("meta"):
        if meta.attrib.get(attr_name) == attr_value and meta.attrib.get("content"):
            return normalize_whitespace(html.unescape(meta.attrib["content"]))
    return ""


def extract_label_value(selector: Selector, labels: Sequence[str]) -> str:
    label_set = {label.strip().lower() for label in labels}
    for node in selector.xpath("//*[normalize-space()]"):
        text = selector_text(node)
        lowered = text.lower()
        if lowered in label_set:
            sibling = node.xpath("following-sibling::*[1]")
            if sibling:
                return clean_extracted_text(selector_text(sibling[0]))
        for label in label_set:
            if lowered.startswith(f"{label}:") or lowered.startswith(f"{label} -"):
                return clean_extracted_text(text.split(":", 1)[-1].split("-", 1)[-1])
    return ""


def looks_like_markup_fragment(value: str) -> bool:
    lowered = value.lower()
    return (
        "<" in value
        or " class=" in lowered
        or 'class="' in lowered
        or " for=" in lowered
        or 'for="' in lowered
        or " id=" in lowered
        or 'id="' in lowered
    )


def clean_extracted_text(value: str) -> str:
    cleaned = normalize_whitespace(value)
    return "" if not cleaned or looks_like_markup_fragment(cleaned) else cleaned


def extract_json_ld_blocks(selector: Selector) -> list[Any]:
    blocks: list[Any] = []
    for raw_block in selector.css('script[type="application/ld+json"]::text').getall():
        try:
            payload = json.loads(html.unescape(raw_block))
        except json.JSONDecodeError:
            continue
        blocks.append(payload)
    return blocks


def iter_json_nodes(payload: Any) -> list[dict[str, Any]]:
    nodes: list[dict[str, Any]] = []
    if isinstance(payload, dict):
        if isinstance(payload.get("@graph"), list):
            for item in payload["@graph"]:
                nodes.extend(iter_json_nodes(item))
        nodes.append(payload)
    elif isinstance(payload, list):
        for item in payload:
            nodes.extend(iter_json_nodes(item))
    return nodes


def extract_json_ld_job_posting(selector: Selector) -> dict[str, Any] | None:
    for block in extract_json_ld_blocks(selector):
        for node in iter_json_nodes(block):
            node_type = node.get("@type")
            if node_type == "JobPosting" or (isinstance(node_type, list) and "JobPosting" in node_type):
                return node
    return None


def format_json_ld_location(location_value: Any) -> str:
    if isinstance(location_value, list):
        parts = [format_json_ld_location(item) for item in location_value]
        return clean_extracted_text(", ".join(part for part in parts if part))
    if isinstance(location_value, str):
        return clean_extracted_text(location_value)
    if not isinstance(location_value, dict):
        return ""
    address = location_value.get("address")
    if isinstance(address, dict):
        parts = [address.get("addressLocality"), address.get("addressRegion"), address.get("addressCountry")]
        return clean_extracted_text(", ".join(str(part) for part in parts if part))
    parts = [
        location_value.get("name"),
        location_value.get("addressLocality"),
        location_value.get("addressRegion"),
        location_value.get("addressCountry"),
    ]
    return clean_extracted_text(", ".join(str(part) for part in parts if part))


def extract_semantic_value(selector: Selector, keys: Sequence[str]) -> str:
    lowered_keys = [key.lower() for key in keys]
    for node in selector.xpath("//*[@id or @class or @data-qa or @data-testid or @for or @name]"):
        attrs = " ".join(str(value).lower() for value in node.attrib.values())
        if not any(key in attrs for key in lowered_keys):
            continue
        if cleaned := clean_extracted_text(selector_text(node)):
            return cleaned
    return ""


def extract_header_text_lines(selector: Selector, max_lines: int = 8) -> list[str]:
    header = selector.xpath("//h1[1]")
    if not header:
        return []
    lines: list[str] = []
    for node in header[0].xpath("following::*[normalize-space()]"):
        text = clean_extracted_text(selector_text(node))
        if text:
            lines.append(text)
        if len(lines) >= max_lines:
            break
    return lines


def looks_like_location_line(line: str) -> bool:
    lowered = line.lower()
    if lowered in {"apply", "summary", "job description", "create a job alert", "create alert", "back to jobs"}:
        return False
    if "remote" in lowered:
        return True
    return line.count(",") >= 1 and len(line) <= 120


def extract_header_location_text(selector: Selector) -> str:
    for line in extract_header_text_lines(selector):
        if looks_like_location_line(line):
            return line
    return ""


def extract_header_remote_text(selector: Selector) -> str:
    for line in extract_header_text_lines(selector):
        if "remote" in line.lower():
            return line
    return ""


def extract_location_text(selector: Selector) -> str:
    job_posting = extract_json_ld_job_posting(selector)
    if job_posting and (location := format_json_ld_location(job_posting.get("jobLocation"))):
        return location
    for candidate in (
        extract_semantic_value(selector, ("candidate-location", "job-location", "location", "locations")),
        extract_label_value(selector, ("Location", "Locations")),
        extract_header_location_text(selector),
    ):
        if cleaned := clean_extracted_text(candidate):
            return cleaned
    return ""


def extract_remote_scope_text(selector: Selector) -> str:
    job_posting = extract_json_ld_job_posting(selector)
    if job_posting:
        remote_parts: list[str] = []
        if isinstance(job_posting.get("jobLocationType"), str):
            remote_parts.append(str(job_posting["jobLocationType"]))
        applicant_scope = job_posting.get("applicantLocationRequirements")
        if applicant_scope:
            remote_parts.append(format_json_ld_location(applicant_scope))
        cleaned = clean_extracted_text(" ".join(part for part in remote_parts if part))
        if cleaned:
            return cleaned
    for candidate in (
        extract_semantic_value(selector, ("candidate-location", "workplace", "remote", "remote-type")),
        extract_label_value(selector, ("Workplace", "Remote", "Remote Type")),
        extract_header_remote_text(selector),
    ):
        if cleaned := clean_extracted_text(candidate):
            if "remote" not in cleaned.lower() and re.search(rf"\bremote\b\s*[:|-]\s*{re.escape(cleaned)}", strip_tags(selector.get())):
                return f"Remote - {cleaned}"
            return cleaned
    return ""


def extract_links_from_html(base_url: str, selector: Selector) -> list[str]:
    urls: list[str] = []
    seen: set[str] = set()
    for href in selector.css("a::attr(href)").getall():
        absolute = urljoin(base_url, href)
        if absolute not in seen:
            seen.add(absolute)
            urls.append(absolute)
    return urls


def shorten_html(source: str, limit: int = 4000) -> str:
    return normalize_whitespace(source or "")[:limit]
