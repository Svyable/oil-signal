from __future__ import annotations

import html

from oilsignal.models import Citation, Report


def _citation_key(citation: Citation) -> tuple[str, str, str, str | None]:
    return (
        str(citation.source_url),
        citation.series_id,
        citation.observation_date.isoformat(),
        citation.calculation_id,
    )


def render_markdown(report: Report) -> str:
    lines = [f"# {report.title}", ""]
    evidence: list[Citation] = []
    evidence_index: dict[tuple[str, str, str, str | None], int] = {}

    for section in report.sections:
        lines.extend([f"## {section.heading}", ""])
        for claim in section.claims:
            refs: list[int] = []
            for citation in claim.citations:
                key = _citation_key(citation)
                if key not in evidence_index:
                    evidence.append(citation)
                    evidence_index[key] = len(evidence)
                refs.append(evidence_index[key])
            suffix = "".join(f"[{ref}]" for ref in refs)
            lines.append(f"- {claim.text} {suffix}")
        lines.append("")

    lines.extend(["## Evidence", ""])
    for index, citation in enumerate(evidence, start=1):
        calc = f"; calculation `{citation.calculation_id}`" if citation.calculation_id else ""
        lines.append(
            f"{index}. {citation.source} `{citation.series_id}` — "
            f"{citation.observation_date.isoformat()}{calc} — {citation.source_url}"
        )
    lines.extend(["", "> Decision support only; not trading or investment advice."])
    return "\n".join(lines)


def render_html(report: Report) -> str:
    markdown = render_markdown(report)
    escaped = html.escape(markdown)
    return f"<!doctype html><html><body><pre>{escaped}</pre></body></html>"


def render_json(report: Report) -> str:
    return report.model_dump_json(indent=2)


def render_report(report: Report, format: str) -> str:
    normalized = format.lower()
    if normalized in {"md", "markdown"}:
        return render_markdown(report)
    if normalized == "html":
        return render_html(report)
    if normalized == "json":
        return render_json(report)
    raise ValueError(f"unsupported report format: {format}")
