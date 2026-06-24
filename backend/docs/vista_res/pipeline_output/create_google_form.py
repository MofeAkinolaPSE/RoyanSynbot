"""
create_google_form.py
---------------------
Creates the SynbotHealth requirements questionnaire as a real Google Form.

Setup (one-time):
  1. Go to https://console.cloud.google.com/
  2. Create a project, enable "Google Forms API" and "Google Drive API"
  3. Create OAuth 2.0 Desktop credentials → download as credentials.json
  4. Place credentials.json in the same folder as this script
  5. Install: pip install google-auth google-auth-oauthlib google-api-python-client

Run:
    python create_google_form.py

The script will open a browser for OAuth consent on first run.
It prints the form URL when done.
"""
import json
import os
from pathlib import Path
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

SCOPES = [
    "https://www.googleapis.com/auth/forms.body",
    "https://www.googleapis.com/auth/drive",
]
SPEC_FILE = Path(__file__).parent / "03_questionnaire_spec.json"
CREDS_FILE = Path(__file__).parent / "credentials.json"
TOKEN_FILE = Path(__file__).parent / "token.json"


def get_credentials():
    creds = None
    if TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(str(CREDS_FILE), SCOPES)
            creds = flow.run_local_server(port=0)
        TOKEN_FILE.write_text(creds.to_json())
    return creds


def add_radio_question(service, form_id, index, title, options):
    service.forms().batchUpdate(
        formId=form_id,
        body={"requests": [{
            "createItem": {
                "item": {
                    "title": title,
                    "questionItem": {
                        "question": {
                            "required": False,
                            "choiceQuestion": {
                                "type": "RADIO",
                                "options": [{"value": o} for o in options],
                            }
                        }
                    }
                },
                "location": {"index": index}
            }
        }]}
    ).execute()


def add_checkbox_question(service, form_id, index, title, options):
    service.forms().batchUpdate(
        formId=form_id,
        body={"requests": [{
            "createItem": {
                "item": {
                    "title": title,
                    "questionItem": {
                        "question": {
                            "required": False,
                            "choiceQuestion": {
                                "type": "CHECKBOX",
                                "options": [
                                    {"value": o["feature"] if isinstance(o, dict) else o}
                                    for o in options
                                ],
                            }
                        }
                    }
                },
                "location": {"index": index}
            }
        }]}
    ).execute()


def add_scale_question(service, form_id, index, title):
    service.forms().batchUpdate(
        formId=form_id,
        body={"requests": [{
            "createItem": {
                "item": {
                    "title": title,
                    "questionItem": {
                        "question": {
                            "required": False,
                            "scaleQuestion": {
                                "low": 1,
                                "high": 5,
                                "lowLabel": "Not critical",
                                "highLabel": "Very critical",
                            }
                        }
                    }
                },
                "location": {"index": index}
            }
        }]}
    ).execute()


def add_text_question(service, form_id, index, title, paragraph=True):
    service.forms().batchUpdate(
        formId=form_id,
        body={"requests": [{
            "createItem": {
                "item": {
                    "title": title,
                    "questionItem": {
                        "question": {
                            "required": False,
                            "textQuestion": {"paragraph": paragraph}
                        }
                    }
                },
                "location": {"index": index}
            }
        }]}
    ).execute()


def add_section_header(service, form_id, index, title):
    service.forms().batchUpdate(
        formId=form_id,
        body={"requests": [{
            "createItem": {
                "item": {
                    "title": title,
                    "pageBreakItem": {}
                },
                "location": {"index": index}
            }
        }]}
    ).execute()


def main():
    with SPEC_FILE.open(encoding="utf-8") as f:
        spec = json.load(f)

    creds   = get_credentials()
    service = build("forms", "v1", credentials=creds)

    # Create blank form
    form = service.forms().create(body={
        "info": {
            "title":       spec["title"],
            "description": spec["description"],
        }
    }).execute()
    form_id = form["formId"]
    print(f"Form created: https://docs.google.com/forms/d/{form_id}/edit")

    idx = 0
    # Intro questions
    for q in spec["intro_questions"]:
        if q["type"] == "radio":
            add_radio_question(service, form_id, idx, q["label"], q["options"])
        else:
            add_text_question(service, form_id, idx, q["label"])
        idx += 1

    # Domain sections
    for section in spec["sections"]:
        add_section_header(service, form_id, idx, f"Section: {section['domain']}")
        idx += 1
        for q in section["questions"]:
            if q["type"] == "radio":
                add_radio_question(service, form_id, idx, q["label"], q["options"])
            elif q["type"] == "checkbox":
                add_checkbox_question(service, form_id, idx, q["label"], q["options"])
            elif q["type"] == "scale":
                add_scale_question(service, form_id, idx, q["label"])
            elif q["type"] == "text":
                add_text_question(service, form_id, idx, q["label"])
            idx += 1

    print(f"\n✓ Questionnaire ready:")
    print(f"  Edit:  https://docs.google.com/forms/d/{form_id}/edit")
    print(f"  Share: https://docs.google.com/forms/d/{form_id}/viewform")


if __name__ == "__main__":
    main()
