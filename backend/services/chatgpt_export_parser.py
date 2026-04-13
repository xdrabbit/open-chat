import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


MARKDOWN_IMAGE_RE = re.compile(r"!\[(?P<alt>[^\]]*)\]\((?P<url>[^)]+)\)")
FILE_ID_RE = re.compile(r"(file_[A-Za-z0-9]+)")
DATE_REFERENCE_RE = re.compile(
    r"\b(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?|\d{1,2}/\d{1,2}/\d{2,4}|20\d{2})\b",
    re.IGNORECASE,
)
LEGAL_HIGH_WEIGHT_PATTERNS = {
    "court_order": re.compile(r"\b(court|order|decree|mandate|hearing|motion|filing|compliance|noncompliance)\b", re.IGNORECASE),
    "property_dispute": re.compile(r"\b(property|sale|listing|showing|realtor|lockbox|mortgage|insurance|contractor)\b", re.IGNORECASE),
    "evidence": re.compile(r"\b(evidence|photo|screenshot|attachment|proof|exhibit|document)\b", re.IGNORECASE),
    "dispute_actor": re.compile(r"\b(attorney|counsel|judge|lender|insurer|opposing|party|broker|commissioner)\b", re.IGNORECASE),
}
LEGAL_MEDIUM_WEIGHT_PATTERNS = {
    "strategy": re.compile(r"\b(strategy|argument|position|remedy|settlement|risk|timeline|chronology|deadline|obligation|duty)\b", re.IGNORECASE),
    "context": re.compile(r"\b(schedule|money|payment|expense|damage|repair|access|communication|response)\b", re.IGNORECASE),
    "emotion_tied_to_case": re.compile(r"\b(stress|pressure|afraid|angry|panic|overwhelmed)\b", re.IGNORECASE),
    "contradiction_context": re.compile(r"\b(contradiction|inconsisten(?:t|cy)|noncompliance|failed to comply|missed deadline)\b", re.IGNORECASE),
}
LEGAL_NEGATIVE_PATTERNS = {
    "software": re.compile(r"\b(code|coding|python|streamlit|debug|repo|commit|pull request|ui|json parser)\b", re.IGNORECASE),
    "creative": re.compile(r"\b(song|music|poem|story|novel|creative writing|lyrics)\b", re.IGNORECASE),
    "general_life": re.compile(r"\b(recipe|shopping|vacation|restaurant|birthday|workout|movie|game|hobby)\b", re.IGNORECASE),
}


def ts_to_str(ts: Optional[float]) -> str:
    if ts is None:
        return "N/A"
    return datetime.fromtimestamp(float(ts)).strftime("%Y-%m-%d %H:%M:%S")


def summarize_text(text: str, limit: int = 220) -> str:
    normalized = " ".join(text.split())
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 3].rstrip() + "..."


def extract_asset_id(value: Any) -> Optional[str]:
    if not value:
        return None
    match = FILE_ID_RE.search(str(value))
    return match.group(1) if match else None


def unique_preserve_order(values: List[str]) -> List[str]:
    result: List[str] = []
    for value in values:
        if value not in result:
            result.append(value)
    return result


def unique_records(records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    result: List[Dict[str, Any]] = []
    seen = set()
    for record in records:
        key = json.dumps(record, sort_keys=True, ensure_ascii=False)
        if key not in seen:
            seen.add(key)
            result.append(record)
    return result


def extract_text_evidence(text: str) -> Tuple[str, List[Dict[str, Any]]]:
    references: List[Dict[str, Any]] = []

    def replace_match(match):
        alt_text = (match.group("alt") or "").strip() or "Uploaded image"
        url = match.group("url").strip()
        asset_id = extract_asset_id(url)
        marker = f"[Referenced image: {alt_text}]"
        references.append({
            "kind": "image_link",
            "label": alt_text,
            "marker": marker,
            "url": url,
            "asset_id": asset_id,
            "filename": None,
            "asset_pointer": None,
        })
        return marker

    cleaned_text = MARKDOWN_IMAGE_RE.sub(replace_match, text)
    return cleaned_text, references


def describe_attachment(part: Any) -> Tuple[Optional[str], Optional[Dict[str, Any]]]:
    if not isinstance(part, dict):
        return None, None

    content_type = str(part.get("content_type") or part.get("type") or "").lower()
    filename = part.get("filename") or part.get("name") or part.get("title")
    asset_pointer = part.get("asset_pointer")
    asset_id = extract_asset_id(asset_pointer)
    url = part.get("url") or part.get("download_url") or part.get("href")

    if "image" in content_type:
        label = "image"
        kind = "image"
    elif "audio" in content_type:
        label = "audio"
        kind = "audio"
    elif "video" in content_type:
        label = "video"
        kind = "video"
    elif "file" in content_type:
        label = "file"
        kind = "file"
    elif asset_pointer:
        label = "attachment"
        kind = "attachment"
    else:
        return None, None

    marker = f"[Attachment: {label} - {filename}]" if filename else f"[Attachment: {label}]"
    return marker, {
        "kind": kind,
        "label": filename or label.title(),
        "marker": marker,
        "url": url,
        "asset_id": asset_id or extract_asset_id(url),
        "filename": filename,
        "asset_pointer": asset_pointer,
    }


def extract_content_text(content: Any) -> Tuple[str, List[str], List[Dict[str, Any]]]:
    if not isinstance(content, dict):
        return "", [], []

    text_segments: List[str] = []
    attachments: List[str] = []
    evidence_refs: List[Dict[str, Any]] = []
    parts = content.get("parts", [])

    for part in parts:
        if isinstance(part, str):
            stripped = part.strip()
            if stripped:
                cleaned_text, extracted_refs = extract_text_evidence(stripped)
                text_segments.append(cleaned_text)
                attachments.extend([record["marker"] for record in extracted_refs])
                evidence_refs.extend(extracted_refs)
            continue

        if isinstance(part, dict):
            text_value = part.get("text")
            if isinstance(text_value, str) and text_value.strip():
                cleaned_text, extracted_refs = extract_text_evidence(text_value.strip())
                text_segments.append(cleaned_text)
                attachments.extend([record["marker"] for record in extracted_refs])
                evidence_refs.extend(extracted_refs)
                continue

            nested_parts = part.get("parts")
            if isinstance(nested_parts, list):
                nested_text, nested_attachments, nested_refs = extract_content_text({"parts": nested_parts})
                if nested_text:
                    text_segments.append(nested_text)
                attachments.extend(nested_attachments)
                evidence_refs.extend(nested_refs)
                continue

            attachment_marker, attachment_ref = describe_attachment(part)
            if attachment_marker:
                attachments.append(attachment_marker)
            if attachment_ref:
                evidence_refs.append(attachment_ref)

    if not parts:
        attachment_marker, attachment_ref = describe_attachment(content)
        if attachment_marker:
            attachments.append(attachment_marker)
        if attachment_ref:
            evidence_refs.append(attachment_ref)

    cleaned_text = "\n\n".join(segment for segment in text_segments if segment).strip()
    unique_attachments = unique_preserve_order(attachments)
    unique_evidence_refs = unique_records(evidence_refs)

    if unique_attachments:
        attachment_block = "\n".join(unique_attachments)
        cleaned_text = f"{cleaned_text}\n\n{attachment_block}".strip() if cleaned_text else attachment_block

    return cleaned_text.strip(), unique_attachments, unique_evidence_refs


def sanitize_filename(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", value.strip())
    return cleaned.strip("._") or "conversation"


def extract_messages_from_conversation(convo: Dict[str, Any]) -> List[Dict[str, Any]]:
    mapping = convo.get("mapping", {})
    messages: List[Dict[str, Any]] = []
    for item in mapping.values():
        msg = item.get("message")
        if msg and msg.get("content"):
            ts = msg.get("create_time")
            role = (msg.get("author") or {}).get("role", "unknown").upper()
            text, attachments, evidence_refs = extract_content_text(msg["content"])
            if text:
                messages.append({
                    "timestamp": ts,
                    "role": role,
                    "content": text,
                    "attachments": attachments,
                    "evidence_refs": evidence_refs,
                })
    messages.sort(key=lambda x: x["timestamp"] if x["timestamp"] else 0)
    return messages


def build_markdown_transcript(convo: Dict[str, Any], messages: List[Dict[str, Any]]) -> str:
    lines = [
        f"# Conversation Transcript: {convo.get('title', 'Untitled')}",
        "",
        "## Metadata",
        f"- Title: {convo.get('title', 'Untitled')}",
        f"- Start: {ts_to_str(convo.get('create_time'))}",
        f"- End: {ts_to_str(convo.get('update_time'))}",
        f"- Message count: {len(messages)}",
        f"- Participants: {', '.join(sorted({message['role'].title() for message in messages})) or 'Unknown'}",
        "",
        "## Transcript",
        "",
    ]

    for index, message in enumerate(messages, 1):
        lines.extend([
            f"### [{index}] {message['role']} - {ts_to_str(message['timestamp'])}",
            "",
            message["content"],
            "",
        ])

    return "\n".join(lines).strip() + "\n"


def build_evidence_manifest(convo: Dict[str, Any], messages: List[Dict[str, Any]]) -> Dict[str, Any]:
    exhibits: List[Dict[str, Any]] = []
    exhibit_number = 1

    for index, message in enumerate(messages, 1):
        for reference in message["evidence_refs"]:
            exhibits.append({
                "exhibit_id": f"EXH-{exhibit_number:03d}",
                "conversation_title": convo.get("title", "Untitled"),
                "message_index": index,
                "timestamp": message["timestamp"],
                "role": message["role"].lower(),
                "kind": reference.get("kind", "attachment"),
                "label": reference.get("label") or reference.get("marker") or "Attachment",
                "marker": reference.get("marker"),
                "filename": reference.get("filename"),
                "asset_id": reference.get("asset_id"),
                "asset_pointer": reference.get("asset_pointer"),
                "source_url": reference.get("url"),
                "message_excerpt": summarize_text(message["content"]),
                "retrieval_note": "Use the asset id, source URL, or original export package to retrieve the full exhibit when needed.",
            })
            exhibit_number += 1

    return {
        "conversation_title": convo.get("title", "Untitled"),
        "create_time": convo.get("create_time"),
        "update_time": convo.get("update_time"),
        "evidence_count": len(exhibits),
        "exhibits": exhibits,
    }


def score_legal_relevance(text: str, evidence_refs: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    evidence_refs = evidence_refs or []
    matched_high = sorted(label for label, pattern in LEGAL_HIGH_WEIGHT_PATTERNS.items() if pattern.search(text))
    matched_medium = sorted(label for label, pattern in LEGAL_MEDIUM_WEIGHT_PATTERNS.items() if pattern.search(text))
    matched_negative = sorted(label for label, pattern in LEGAL_NEGATIVE_PATTERNS.items() if pattern.search(text))
    has_date_reference = bool(DATE_REFERENCE_RE.search(text))

    score = len(matched_high) * 4 + len(matched_medium) * 2 - len(matched_negative) * 4
    if has_date_reference and (matched_high or matched_medium):
        score += 2
    if evidence_refs:
        score += 2

    if matched_high and matched_negative and score < 8:
        classification = "uncertain"
    elif score >= 8 or (len(matched_high) >= 2 and score >= 6):
        classification = "legal_core"
    elif score >= 3 or matched_high or len(matched_medium) >= 2:
        classification = "legal_adjacent"
    elif score <= -4 and not matched_high and not matched_medium:
        classification = "non_legal"
    else:
        classification = "uncertain"

    return {
        "score": score,
        "classification": classification,
        "matched_high": matched_high,
        "matched_medium": matched_medium,
        "matched_negative": matched_negative,
        "has_date_reference": has_date_reference,
        "has_evidence_refs": bool(evidence_refs),
    }


def summarize_message_ranges(indices: List[int]) -> List[str]:
    if not indices:
        return []

    ranges = []
    start = prev = indices[0]
    for value in indices[1:]:
        if value == prev + 1:
            prev = value
            continue
        ranges.append(f"{start}-{prev}" if start != prev else str(start))
        start = prev = value
    ranges.append(f"{start}-{prev}" if start != prev else str(start))
    return ranges


def build_legal_relevance_manifest(convo: Dict[str, Any], messages: List[Dict[str, Any]]) -> Dict[str, Any]:
    classified_messages: List[Dict[str, Any]] = []
    thread_score = 0
    counts = {"legal_core": 0, "legal_adjacent": 0, "non_legal": 0, "uncertain": 0}

    for index, message in enumerate(messages, 1):
        relevance = score_legal_relevance(message["content"], message["evidence_refs"])
        thread_score += relevance["score"]
        counts[relevance["classification"]] += 1
        classified_messages.append({
            "message_index": index,
            "timestamp": message["timestamp"],
            "role": message["role"].lower(),
            "classification": relevance["classification"],
            "score": relevance["score"],
            "matched_high": relevance["matched_high"],
            "matched_medium": relevance["matched_medium"],
            "matched_negative": relevance["matched_negative"],
            "has_date_reference": relevance["has_date_reference"],
            "has_evidence_refs": relevance["has_evidence_refs"],
            "excerpt": summarize_text(message["content"], 220),
        })

    included_indices = [
        item["message_index"]
        for item in classified_messages
        if item["classification"] in {"legal_core", "legal_adjacent"}
    ]
    range_summary = summarize_message_ranges(included_indices)
    mixed_domain = bool((counts["legal_core"] or counts["legal_adjacent"]) and counts["non_legal"])

    if counts["legal_core"] >= 2 or thread_score >= 18:
        thread_classification = "legal_core" if not mixed_domain else "uncertain"
    elif counts["legal_core"] or counts["legal_adjacent"]:
        thread_classification = "legal_adjacent" if not mixed_domain else "uncertain"
    elif counts["non_legal"] and not counts["uncertain"]:
        thread_classification = "non_legal"
    else:
        thread_classification = "uncertain"

    return {
        "conversation_title": convo.get("title", "Untitled"),
        "thread_classification": thread_classification,
        "thread_score": thread_score,
        "mixed_domain": mixed_domain,
        "message_counts": counts,
        "included_message_ranges": range_summary,
        "included_message_count": len(included_indices),
        "messages": classified_messages,
    }


def map_archive_type(legal_manifest: Dict[str, Any]) -> Tuple[str, bool]:
    classification = legal_manifest.get("thread_classification")
    mixed_domain = bool(legal_manifest.get("mixed_domain"))
    legal_sensitive = bool(
        legal_manifest.get("message_counts", {}).get("legal_core")
        or legal_manifest.get("message_counts", {}).get("legal_adjacent")
    )

    if classification == "legal_core":
        return "legal_reference", True
    if classification in {"legal_adjacent", "uncertain"} and mixed_domain:
        return "mixed_archive", True
    if classification == "legal_adjacent":
        return "mixed_archive", True
    return "archive_chat", legal_sensitive


def build_era_label(convo: Dict[str, Any]) -> Optional[str]:
    timestamp = convo.get("update_time") or convo.get("create_time")
    if not timestamp:
        return None
    return datetime.fromtimestamp(float(timestamp)).strftime("%B %Y")


def parse_chatgpt_export_data(data: Any, source_name: str = "conversations.json") -> List[Dict[str, Any]]:
    if not isinstance(data, list):
        return []

    threads: List[Dict[str, Any]] = []
    for index, convo in enumerate(data, 1):
        if not isinstance(convo, dict) or not convo.get("mapping"):
            continue

        title = convo.get("title") or f"Untitled conversation {index}"
        messages = extract_messages_from_conversation(convo)
        if not messages:
            continue

        evidence_manifest = build_evidence_manifest(convo, messages)
        legal_manifest = build_legal_relevance_manifest(convo, messages)
        archive_type, legal_sensitive = map_archive_type(legal_manifest)
        era_label = build_era_label(convo)
        file_stem = sanitize_filename(title)
        thread_filename = f"{file_stem}.chatgpt.md"
        transcript_markdown = build_markdown_transcript(convo, messages)

        threads.append({
            "source_name": source_name,
            "title": title,
            "thread_filename": thread_filename,
            "text": transcript_markdown,
            "archive_type": archive_type,
            "legal_sensitivity": legal_sensitive,
            "era_label": era_label,
            "message_count": len(messages),
            "evidence_count": evidence_manifest["evidence_count"],
            "participants": sorted({message["role"].lower() for message in messages}),
            "create_time": convo.get("create_time"),
            "update_time": convo.get("update_time"),
            "legal_relevance_manifest": legal_manifest,
            "evidence_manifest": evidence_manifest,
        })

    return threads


def parse_chatgpt_export_file(file_path: str) -> List[Dict[str, Any]]:
    path = Path(file_path)
    with open(path, "r", encoding="utf-8") as handle:
        data = json.load(handle)
    return parse_chatgpt_export_data(data, source_name=path.name)
