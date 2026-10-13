# iPhone Shortcut: photo → meal log

Shortcut flow: ask for meal name + optional details → camera or photo
library → AI analyzes the photo → for each food component: search the
catalog, create it if missing, log it under the meal with an estimated
weight.

Base URL: `http://cachyos-horus:8877` (or `http://100.127.136.124:8877`
if the Tailscale name doesn't resolve from the phone).

## 1. AI prompt (paste into the "Get AI Response" action's instructions)

```
You are a food-logging assistant. A user is logging a meal.

Meal name (already chosen by the user): {{meal_name}}
User's notes about the meal (may be empty): {{details}}
Attached photo: the meal the user is logging.

Your task:
1. Identify each distinct food component in the photo (e.g. "Spicy
   Chicken with Sauce", "White Rice", "Grilled Broccoli"). Use the
   user's notes when they help identify what something is.
2. For each component, estimate: a standard reference serving size, its
   nutrition per that serving, and how much is actually present in the
   photo.

Respond with ONLY one valid JSON object — no markdown, no code fences,
no explanation, nothing before or after:

{
  "items": [
    {
      "name": "Spicy Chicken with Sauce",
      "serving_size": 150,
      "weight": 150,
      "calories": 320,
      "protein": 30,
      "fat_total": 18,
      "carbs_total": 10,
      "fiber_total": 2,
      "sugars_total": 3,
      "added_sugars_total": 3,
      "sugar_alcohols_total": 0,
      "sodium": 600,
      "fat_saturated": 6,
      "cholesterol": 90
    }
  ]
}

Rules:
- Every number MUST be a bare JSON number. Never an empty string, never
  a unit suffix, never text. If you cannot estimate a number, use 0.
- serving_size: grams for a standard reference portion of a weighed
  food (e.g. 100, 150); exactly 1 for whole/portion items (a sandwich,
  a slice, a scoop, a can).
- weight: the estimated amount of this component present in the photo,
  in the SAME units as serving_size (grams, or a count for whole items).
- Macros are per reference serving (per serving_size), not per photo
  amount.
- Names: plain descriptive text under 60 characters, consistent so
  future photos of the same food match the same name (e.g. "Taco Bell
  Steak Quesadilla").
- List only components that are clearly in the photo, no more than 8
  items; if unsure whether something is food, omit it.
- Balance all braces/brackets; no trailing commas; the output must
  parse as JSON.
```

## 2. Shortcut actions (in order)

1. **Ask for Input** → "Meal name?" (e.g. "Lunch at Taco Bell") → variable
   `meal_name`.
2. **Ask for Input** → "Details (optional)? e.g. restaurant, extras" →
   variable `details`. Mark it **optional / allow skip**.
3. **Get Photo** — at runtime this offers camera or photo library →
   variable `photo`.
4. **Get AI Response** — instructions = the prompt above (with
   `{{meal_name}}` and `{{details}}` inserted), photo attached →
   variable `ai_text`.
5. **Guard** — **If** `ai_text` **Text Contains** `""` (two literal
   double-quote characters) → **Show Notification**
   "AI left numbers empty — run the shortcut again" and stop.
6. **Get JSON Value** on `ai_text`, path `items` → variable `items`.
7. **Get Current Date** → **Date Format** `yyyyMMdd` → variable `today`.
8. **Repeat with Each Item** (over `items`):
   1. **Get JSON Value** item, `name` → `name`.
   2. **Encode URL Component** `name` → `name_enc`.
   3. **Send HTTP Request** GET
      `http://cachyos-horus:8877/api/foods?q={{name_enc}}` →
      `search_resp`.
   4. **Get Length** `search_resp` → `match_count`.
   5. **If** `match_count` > 0:
      - **Get JSON Value** `search_resp`, path `0.name` → `food_name`.
   6. **Else** (not in catalog):
      - **Send HTTP Request** POST
        `http://cachyos-horus:8877/api/foods` — **Body: JSON**, body =
        the `item` dictionary from the loop (do NOT re-extract the 14
        fields; the item already has exactly the right keys, and the
        extra `weight` key is ignored). A 409 response is fine.
      - Set `food_name` = `name`.
   7. **Get JSON Value** item, `weight` → `weight` (stays a number).
   8. **Construct JSON Dictionary**: `food` = `food_name`,
      `weight` = `weight`, `meal` = `meal_name`.
   9. **Send HTTP Request** POST
      `http://cachyos-horus:8877/api/days/{{today}}/items` —
      **Body: JSON**, body = that dictionary.
   10. **If Any Error** on that request → **Show Notification**:
       `Item log failed for {{name}}: {{Response Body}}`.
9. **Show Notification**: `Logged {{meal_name}}`.

## Notes / why

- **Body: JSON** on every "Send HTTP Request" sets the correct
  `Content-Type` and keeps numbers as JSON numbers (the old shortcut's
  422s came from stringified numbers).
- `Get Length` before `0.name` because indexing an empty array errors
  with "no value was found for dictionary in key '0'".
- The catalog is the single source of truth for macros: once a food is
  created (with the AI's estimate), every future log of that name uses
  the stored macros.
- Server-side, rejected API writes are logged with their bodies as
  `[api-reject]` lines — check `podman logs food-dashboard` when
  something fails.
