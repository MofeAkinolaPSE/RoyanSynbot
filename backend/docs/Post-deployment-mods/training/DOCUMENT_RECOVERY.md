# Legacy Patient Documents — why they can't be opened, and how to recover them

**Short answer:** the files were never in the database we were given. Hope stored
them on disk and kept only a pointer in the database. We received the SQL dump; we
did not receive the folder the files live in.

They are very likely still recoverable. This is a missing-handover problem, not a
data-loss problem.

---

## What the evidence shows

Hope's `patient_documents` table has both a `file` column and a `link` column.
Across all **9,192** rows in the dump:

| Field | Populated |
|---|---|
| `file` (the blob) | **0** |
| `link` (a path/URL) | **0** |
| `filename` | 9,192 |
| `size` | 9,113 |

So every row knows the file's **name**, **MIME type**, **size** and **description** —
but carries no bytes and no path.

Filenames follow an upload convention that confirms disk storage:

```
pt_img_1477298755.docx     ← prefix + unix timestamp
ohno_1481717790.jpg
```

That is a classic PHP upload pattern: move the file into an uploads directory under a
generated name, store the name in the database.

**Total referenced: 1.91 GB**, and the mix is exactly what you would expect from a
records room:

| Type | Count |
|---|---|
| JPEG / JPG | 4,883 |
| PDF | 3,974 |
| BMP | 69 |

Scanned lab results, referral letters, consent forms, ID cards.

---

## What this means

- We hold a complete, accurate **index**: which patient, what the document is, when
  it was filed, who filed it, how big it is.
- We do not hold the images themselves.
- `royan_patient_documents.is_migrated` is set to `false` on every row precisely so
  the app never implies a file is openable when it is not.

Showing the index is still worth it: a clinician can see that a 2019 FBS result
exists for this patient and go and ask for it, which beats believing the record began
at go-live.

---

## How to recover them

Ask Royan's IT (or whoever holds the Hope server) for **the uploads directory**, not
another database dump. Another dump will contain exactly what we already have.

What to ask for:
- The web root / uploads folder from the Hope application server — often something
  like `.../RhosP/uploads/`, `/files/`, or `/webroot/img/`
- Any filesystem backup of that server
- Roughly **1.91 GB**, ~9,200 files

Once we have it, re-linking is straightforward: `filename` is unique per row, so we
match on name, copy the files into our own document storage, and flip `is_migrated`
to `true`. No re-migration of anything else, no downtime, and the existing document
cards start opening.

Worth asking soon — decommissioned servers get wiped, and this is the one piece of
the legacy record that cannot be reconstructed from anything else.

---

## Meanwhile

Say it plainly in training, in the pharmacy and clinical walkthroughs:

> "You'll see old documents listed on a patient's chart with a description and a
> date. Those came across as an index — the scans themselves are still on the old
> system, and we're arranging to bring them over. If you need one now, the old
> record is the place to ask."

Staff will click one on day one. Better they hear it from us first.
