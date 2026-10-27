import re
import logging
from .invoice_schema import Invoice, InvoiceType, TaskDomain

logger = logging.getLogger(__name__)

NL = "\n"


class InvoiceParser:

    @staticmethod
    def parse_dispatch(response, project_id):
        invoice = Invoice(
            invoice_id="disp_" + project_id,
            type=InvoiceType.DISPATCH,
            from_model="gemma",
            to_model="claude",
            project_id=project_id,
            raw_text=response,
        )
        domain_match = re.search(r"DOMAIN:\s*(\w+)", response, re.I)
        if domain_match:
            try:
                invoice.domain = TaskDomain(domain_match.group(1).lower())
            except ValueError:
                invoice.domain = TaskDomain.CODING

        summary_match = re.search(r"SUMMARY:\s*(.+)", response, re.I | re.MULTILINE)
        if summary_match:
            invoice.summary = summary_match.group(1).strip()

        req_section = re.search(
            r"REQUIREMENTS:\s*\n([\s\S]*?)(?=\n[A-Z_]+:|$)", response, re.I
        )
        if req_section:
            reqs = re.findall(r"-\s*(.+)", req_section.group(1))
            invoice.requirements = [r.strip() for r in reqs if r.strip()]

        const_section = re.search(
            r"CONSTRAINTS:\s*\n([\s\S]*?)(?=\n[A-Z_]+:|$)", response, re.I
        )
        if const_section:
            consts = re.findall(r"-\s*(.+)", const_section.group(1))
            invoice.constraints = [c.strip() for c in consts if c.strip()]

        return invoice

    @staticmethod
    def parse_plan(response, project_id):
        invoice = Invoice(
            invoice_id="plan_" + project_id,
            type=InvoiceType.PLAN,
            from_model="claude",
            to_model="qwen_coder",
            project_id=project_id,
            raw_text=response,
        )
        lang_match = re.search(r"LANGUAGE:\s*(\w+)", response, re.I)
        if lang_match:
            invoice.architecture["language"] = lang_match.group(1).strip()

        files_section = re.search(
            r"FILES:\s*\n([\s\S]*?)(?=\n[A-Z_]+:|$)", response, re.I
        )
        if files_section:
            file_blocks = re.findall(
                r"-\s*name:\s*(.+?)(?:\n|$)", files_section.group(1)
            )
            for name in file_blocks:
                invoice.file_structure.append({"name": name.strip(), "purpose": ""})

        req_section = re.search(
            r"REQUIREMENTS:\s*\n([\s\S]*?)(?=\n[A-Z_]+:|$)", response, re.I
        )
        if req_section:
            reqs = re.findall(r"-\s*(.+)", req_section.group(1))
            invoice.requirements = [r.strip() for r in reqs if r.strip()]

        return invoice

    @staticmethod
    def parse_review(response, project_id):
        invoice = Invoice(
            invoice_id="review_" + project_id,
            type=InvoiceType.REVIEW,
            from_model="claude",
            to_model="qwen_coder",
            project_id=project_id,
            raw_text=response,
        )
        grade_match = re.search(r"GRADE:\s*([A-F])", response, re.I)
        if grade_match:
            invoice.grade = grade_match.group(1).upper()

        verdict_match = re.search(
            r"VERDICT:\s*(APPROVED|NEEDS_FIX|REJECTED)", response, re.I
        )
        if verdict_match:
            invoice.verdict = verdict_match.group(1).upper()
        else:
            invoice.verdict = "APPROVED" if invoice.grade in ("A", "B") else "NEEDS_FIX"

        issues_section = re.search(
            r"ISSUES_FOUND:\s*\n([\s\S]*?)(?=\n[A-Z_]+:|$)", response, re.I
        )
        if issues_section:
            text = issues_section.group(1)
            severity_matches = re.findall(r"severity:\s*(\w+)", text, re.I)
            file_matches = re.findall(r"file:\s*(.+?)(?:\n|$)", text, re.I)
            desc_matches = re.findall(r"description:\s*(.+?)(?:\n|$)", text, re.I)
            limit = min(len(severity_matches), len(desc_matches))
            for i in range(limit):
                sev = severity_matches[i].lower() if i < len(severity_matches) else "medium"
                fl = file_matches[i].strip() if i < len(file_matches) else "unknown"
                desc = desc_matches[i].strip() if i < len(desc_matches) else ""
                invoice.issues.append(
                    {"severity": sev, "file": fl, "description": desc}
                )

        return invoice
