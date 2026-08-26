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


def _index_evidence(report: Report) -> tuple[list[Citation], dict[tuple[str, str, str, str | None], int]]:
    evidence: list[Citation] = []
    evidence_index: dict[tuple[str, str, str, str | None], int] = {}
    for claim in report.iter_claims():
        for citation in claim.citations:
            key = _citation_key(citation)
            if key not in evidence_index:
                evidence.append(citation)
                evidence_index[key] = len(evidence)
    return evidence, evidence_index


def render_markdown(report: Report) -> str:
    evidence, evidence_index = _index_evidence(report)
    lines = [f"# {report.title}", ""]

    for section in report.sections:
        lines.extend([f"## {section.heading}", ""])
        for claim in section.claims:
            refs = [evidence_index[_citation_key(citation)] for citation in claim.citations]
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
    evidence, evidence_index = _index_evidence(report)
    parts = ["<!doctype html><html><body>", f"<h1>{html.escape(report.title)}</h1>"]
    for section in report.sections:
        parts.append(f"<h2>{html.escape(section.heading)}</h2><ul>")
        for claim in section.claims:
            refs = []
            for citation in claim.citations:
                index = evidence_index[_citation_key(citation)]
                refs.append(f'<a href="#evidence-{index}">[{index}]</a>')
            parts.append(f"<li>{html.escape(claim.text)} {' '.join(refs)}</li>")
        parts.append("</ul>")
    parts.append("<h2>Evidence</h2><ol>")
    for index, citation in enumerate(evidence, start=1):
        source_url = html.escape(str(citation.source_url), quote=True)
        label = html.escape(
            f"{citation.source} {citation.series_id} — {citation.observation_date.isoformat()}"
        )
        parts.append(
            f'<li id="evidence-{index}"><a href="{source_url}">{label}</a></li>'
        )
    parts.append("</ol><p><em>Decision support only; not trading or investment advice.</em></p>")
    parts.append("</body></html>")
    return "".join(parts)


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
