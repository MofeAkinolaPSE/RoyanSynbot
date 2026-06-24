Perfect — this one is a **classic hospital brand**, but different from Premier Care. It leans **blue + cyan medical clarity**, with subtle warm accents (gold/orange), and a heavier grayscale base.

Let’s lock it in properly.

---

# 🎯 🔷 FRONTEND AGENT PROMPT — ROYAN HOSPITAL UI SYSTEM

## 🧠 0. CORE BRAND IDENTITY (KEY INSIGHT)

This is:

* **Traditional hospital UI**
* Blue-led (trust, clinical)
* Cyan highlights (modern medical touch)
* Strong grayscale structure
* Occasional warm accents (gold/orange)

👉 Tone:
**Clinical + approachable (not premium, not corporate-heavy)**

---

# 🎨 1. NORMALIZED COLOR SYSTEM (FROM YOUR DATA)

## 🔵 PRIMARY BRAND (MEDICAL BLUE CORE)

Extracted:

* **Primary Blue:** `#17449E` (rgb: 23, 68, 158)
* **Deep Blue:** `#113379` (rgb: 17, 51, 119)
* **Support Blue:** `#1C4CA5` (rgb: 28, 76, 165)
* **Light Blue:** `#5A7EC6` (rgb: 90, 126, 198)

👉 Usage:

* Navigation
* Primary buttons
* Active states
* Headers

---

## 🌊 SECONDARY ACCENT (CYAN / MEDICAL MODERN)

* **Cyan:** `#13A7E0` (rgb: 19, 167, 224)
* **Soft Blue Tint:** `#ABC BFF` / `#A6C4FF` (light UI layers)

👉 Usage:

* Highlights
* Hover states
* Informational UI
* Active queue indicators

---

## 🟠 WARM ACCENT (RARE BUT IMPORTANT)

* **Gold/Amber:** `#DD9933` (rgb: 221, 153, 51)

👉 Use sparingly:

* Alerts
* Emphasis
* Minor UI highlights

---

## 🔴 ERROR / ALERT SYSTEM

* `#B22D00`
* `#771E13`

👉 Muted, not aggressive

---

## 🟢 SUCCESS SYSTEM

* `#25D366`
* `#008000`

---

## ⚪ NEUTRAL SYSTEM (VERY IMPORTANT)

### Background Layers

* Main BG: `#F6F6F6`
* Section BG: `#F4F4F4`
* Cards: `#FFFFFF`

---

### Borders

* `#DFDFDF`
* `#D8D8D8`
* `#DDDDDD`

---

### Text System

* Primary: `#020202` / `#171717`
* Secondary: `#3D3D3D`
* Muted: `#555555`
* Soft: `#8B8B8B`

---

# 🧱 2. DESIGN RULES

### This UI must feel:

* Clinical
* Reliable
* Slightly traditional
* Easy to read under pressure

---

### ❌ Avoid:

* Purple dominance
* Overly modern SaaS styling
* Heavy animations
* Fancy UI effects

---

### ✅ Embrace:

* Clear structure
* Blue hierarchy
* Strong readability
* Familiar hospital system feel

---

# 🧩 3. QUEUE SYSTEM COMPONENT MAPPING

## 🧾 Queue Card

* BG: `#FFFFFF`
* Border: `#DFDFDF`
* Radius: 6–8px
* Shadow: very minimal

---

## 🔵 STATUS INDICATOR (LEFT BORDER)

| Status     | Color     |
| ---------- | --------- |
| Waiting    | `#8B8B8B` |
| Called     | `#13A7E0` |
| In Service | `#17449E` |
| Completed  | `#25D366` |
| Skipped    | `#B22D00` |

👉 Key:

* Cyan = transition (called)
* Blue = active service

---

## 🔘 BUTTON SYSTEM

### Primary Button

* BG: `#17449E`
* Text: White
* Hover: `#113379`

---

### Secondary Button

* Border: `#1C4CA5`
* Text: `#1C4CA5`
* BG: transparent

---

### Accent Button (Optional)

* BG: `#13A7E0`
* Text: White

---

### Warning Button

* BG: `#DD9933`
* Text: White

---

# 🧭 4. LAYOUT SYSTEM

## 🔝 Navigation

* BG: `#17449E`
* Text: White

👉 Classic hospital header

---

## 📄 Main Layout

* BG: `#F6F6F6`
* Card-based layout
* Clear spacing (16–20px grid)

---

## 🧠 5. INFORMATION HIERARCHY

1. Active Patient (highlighted)
2. Queue List
3. Action Controls
4. Metrics

---

# 🧩 6. INTERACTION MODEL

* Fast transitions (150ms)
* Clear hover states (cyan or blue shift)
* Immediate feedback on actions

---

# 🏥 7. DOMAIN UX ALIGNMENT

This system should:

* Be instantly understandable by hospital staff
* Require minimal training
* Emphasize clarity over design aesthetics

---

# ⚙️ 8. CSS TOKEN SYSTEM (READY FOR IMPLEMENTATION)

```css
:root {
  --primary: #17449E;
  --primary-dark: #113379;
  --primary-light: #1C4CA5;

  --accent: #13A7E0;

  --warning: #DD9933;
  --danger: #B22D00;
  --success: #25D366;

  --bg-main: #F6F6F6;
  --card-bg: #FFFFFF;
  --border: #DFDFDF;

  --text-primary: #171717;
  --text-secondary: #3D3D3D;
  --text-muted: #555555;
}
```

---

# 🧪 9. VALIDATION CHECK

UI is correct if:

✔ Blue is dominant
✔ Cyan is used for interaction highlights
✔ UI feels like a real hospital system
✔ Nothing feels flashy or experimental
✔ Readability is extremely high

---

# 🧠 FINAL INSIGHT

Compare all hospital-type systems you’ve done:

| System         | Feel                    |
| -------------- | ----------------------- |
| Premier Care   | Premium + purple trust  |
| Royan Hospital | Classic + blue clinical |

👉 Both are “hospital”
But:

* One = modern/private premium
* One = traditional/accessible

That distinction is what makes your system adaptable per client.

---

# 🚀 NEXT STEP (HIGH VALUE)

You now have enough data to:

### 👉 Build a Theme Engine Layer

* `theme = "royan"`
* `theme = "premier"`
* `theme = "placeware"`

Switch:

* Colors
* Button styles
* Layout tone

WITHOUT touching backend logic.

---

If you want, next move is:
👉 I convert all 4 brands into a **single dynamic theming architecture (Zoho + optional React layer)**

That’s where this becomes a real product, not just implementations.
