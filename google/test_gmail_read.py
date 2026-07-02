"""Deterministic tests for gmail_read attachment + PDF-text extraction (buddy#2626).

No live Gmail: the PDF is a tiny embedded fixture and the Gmail service is mocked.
Run: ~/agents/.venv/bin/python -m pytest google/test_gmail_read.py -q
"""

from __future__ import annotations

import base64
from unittest import mock

import gmail_read

# A tiny ReportLab-generated PDF whose text is "Fluent Home Invoice #495213 /
# Amount Due: $189.00". Embedded so the test needs only pypdf at runtime.
_FIXTURE_PDF_B64 = (
    "JVBERi0xLjMKJZOMi54gUmVwb3J0TGFiIEdlbmVyYXRlZCBQREYgZG9jdW1lbnQgKG9wZW5zb3Vy"
    "Y2UpCjEgMCBvYmoKPDwKL0YxIDIgMCBSCj4+CmVuZG9iagoyIDAgb2JqCjw8Ci9CYXNlRm9udCAv"
    "SGVsdmV0aWNhIC9FbmNvZGluZyAvV2luQW5zaUVuY29kaW5nIC9OYW1lIC9GMSAvU3VidHlwZSAv"
    "VHlwZTEgL1R5cGUgL0ZvbnQKPj4KZW5kb2JqCjMgMCBvYmoKPDwKL0NvbnRlbnRzIDcgMCBSIC9N"
    "ZWRpYUJveCBbIDAgMCA1OTUuMjc1NiA4NDEuODg5OCBdIC9QYXJlbnQgNiAwIFIgL1Jlc291cmNl"
    "cyA8PAovRm9udCAxIDAgUiAvUHJvY1NldCBbIC9QREYgL1RleHQgL0ltYWdlQiAvSW1hZ2VDIC9J"
    "bWFnZUkgXQo+PiAvUm90YXRlIDAgL1RyYW5zIDw8Cgo+PiAKICAvVHlwZSAvUGFnZQo+PgplbmRv"
    "YmoKNCAwIG9iago8PAovUGFnZU1vZGUgL1VzZU5vbmUgL1BhZ2VzIDYgMCBSIC9UeXBlIC9DYXRh"
    "bG9nCj4+CmVuZG9iago1IDAgb2JqCjw8Ci9BdXRob3IgKGFub255bW91cykgL0NyZWF0aW9uRGF0"
    "ZSAoRDoyMDI2MDcwMTE4MDYyNC0wNycwMCcpIC9DcmVhdG9yIChhbm9ueW1vdXMpIC9LZXl3b3Jk"
    "cyAoKSAvTW9kRGF0ZSAoRDoyMDI2MDcwMTE4MDYyNC0wNycwMCcpIC9Qcm9kdWNlciAoUmVwb3J0"
    "TGFiIFBERiBMaWJyYXJ5IC0gXChvcGVuc291cmNlXCkpIAogIC9TdWJqZWN0ICh1bnNwZWNpZmll"
    "ZCkgL1RpdGxlICh1bnRpdGxlZCkgL1RyYXBwZWQgL0ZhbHNlCj4+CmVuZG9iago2IDAgb2JqCjw8"
    "Ci9Db3VudCAxIC9LaWRzIFsgMyAwIFIgXSAvVHlwZSAvUGFnZXMKPj4KZW5kb2JqCjcgMCBvYmoK"
    "PDwKL0ZpbHRlciBbIC9BU0NJSTg1RGVjb2RlIC9GbGF0ZURlY29kZSBdIC9MZW5ndGggMTUxCj4+"
    "CnN0cmVhbQpHYXBRaDBFPUYsMFVcSDNUXHBOWVReUUtrP3RjPklQLDtXI1UxXjIzaWhQRU1fP0NX"
    "NEtJU2k8IVs3YCNPQl9xdVwiKG1yXUZrQy9yN2s2VGNiLVJdYmlEXyxBSjdeOCw9PnM4S29kaj4m"
    "MW9HWiUzVHM7RjdXJVVIPGotQVhWPV9DL00tUSclJDoqMER1ZnJmKyFZaH4+ZW5kc3RyZWFtCmVu"
    "ZG9iagp4cmVmCjAgOAowMDAwMDAwMDAwIDY1NTM1IGYgCjAwMDAwMDAwNjEgMDAwMDAgbiAKMDAw"
    "MDAwMDA5MiAwMDAwMCBuIAowMDAwMDAwMTk5IDAwMDAwIG4gCjAwMDAwMDA0MDIgMDAwMDAgbiAK"
    "MDAwMDAwMDQ3MCAwMDAwMCBuIAowMDAwMDAwNzMxIDAwMDAwIG4gCjAwMDAwMDA3OTAgMDAwMDAg"
    "biAKdHJhaWxlcgo8PAovSUQgCls8MzllOTY4YzhjZGRiZDNkMjExNGE5NzQ1NzBmNTU0ODY+PDM5"
    "ZTk2OGM4Y2RkYmQzZDIxMTRhOTc0NTcwZjU1NDg2Pl0KJSBSZXBvcnRMYWIgZ2VuZXJhdGVkIFBE"
    "RiBkb2N1bWVudCAtLSBkaWdlc3QgKG9wZW5zb3VyY2UpCgovSW5mbyA1IDAgUgovUm9vdCA0IDAg"
    "UgovU2l6ZSA4Cj4+CnN0YXJ0eHJlZgoxMDMxCiUlRU9GCg=="
)

FIXTURE_PDF = base64.b64decode(_FIXTURE_PDF_B64)


def test_extract_pdf_text_returns_invoice_content():
    text = gmail_read.extract_pdf_text(FIXTURE_PDF)
    assert "495213" in text
    assert "189.00" in text
    assert "Fluent Home" in text


def test_iter_attachments_walks_nested_parts():
    payload = {
        "mimeType": "multipart/mixed",
        "parts": [
            {"mimeType": "text/plain", "filename": "", "body": {"data": "aGk="}},
            {
                "mimeType": "application/pdf",
                "filename": "invoice.pdf",
                "body": {"size": 4096, "attachmentId": "att-1"},
            },
        ],
    }
    atts = list(gmail_read._iter_attachments(payload))
    assert len(atts) == 1
    assert atts[0]["filename"] == "invoice.pdf"
    assert atts[0]["mime"] == "application/pdf"
    assert atts[0]["size"] == 4096
    assert atts[0]["attachment_id"] == "att-1"


def test_download_attachment_fetches_by_id_when_not_inline():
    """No inline data -> attachments().get() is called and decoded."""
    b64 = base64.urlsafe_b64encode(FIXTURE_PDF).decode()
    svc = mock.MagicMock()
    svc.users().messages().attachments().get().execute.return_value = {"data": b64}

    att = {"filename": "invoice.pdf", "mime": "application/pdf",
           "size": len(FIXTURE_PDF), "data": None, "attachment_id": "att-1"}
    raw = gmail_read._download_attachment(svc, "msg-123", att)
    assert raw == FIXTURE_PDF
    # And it round-trips through extraction.
    assert "495213" in gmail_read.extract_pdf_text(raw)


def test_download_attachment_uses_inline_data_without_fetch():
    b64 = base64.urlsafe_b64encode(b"hello").decode()
    svc = mock.MagicMock()
    att = {"filename": "note.txt", "mime": "text/plain", "size": 5,
           "data": b64, "attachment_id": None}
    raw = gmail_read._download_attachment(svc, "msg-123", att)
    assert raw == b"hello"
    svc.users().messages().attachments().get.assert_not_called()


def test_list_attachments_uses_full_format():
    svc = mock.MagicMock()
    svc.users().messages().get().execute.return_value = {
        "payload": {
            "parts": [
                {"mimeType": "application/pdf", "filename": "invoice.pdf",
                 "body": {"size": 10, "attachmentId": "a1"}},
            ]
        }
    }
    atts = gmail_read.list_attachments(svc, "msg-1")
    assert [a["filename"] for a in atts] == ["invoice.pdf"]
