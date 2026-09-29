from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor

out_path = r"C:\Users\Jun_hui_Yew\OneDrive - Dell Technologies\Desktop\poc\Predictive_Preloading_PoC_Presentation.pptx"

prs = Presentation()

# Theme helpers
TITLE_COLOR = RGBColor(15, 48, 82)
BODY_COLOR = RGBColor(45, 55, 72)
ACCENT = RGBColor(0, 122, 204)


def add_title_slide(title, subtitle):
    slide = prs.slides.add_slide(prs.slide_layouts[0])
    slide.shapes.title.text = title
    slide.placeholders[1].text = subtitle
    t = slide.shapes.title.text_frame.paragraphs[0].runs[0].font
    t.size = Pt(42)
    t.bold = True
    t.color.rgb = TITLE_COLOR
    s = slide.placeholders[1].text_frame.paragraphs[0].runs[0].font
    s.size = Pt(20)
    s.color.rgb = BODY_COLOR


def add_bullets_slide(title, bullets, notes=None):
    slide = prs.slides.add_slide(prs.slide_layouts[1])
    slide.shapes.title.text = title
    title_run = slide.shapes.title.text_frame.paragraphs[0].runs[0].font
    title_run.color.rgb = TITLE_COLOR
    title_run.bold = True

    tf = slide.placeholders[1].text_frame
    tf.clear()
    for idx, item in enumerate(bullets):
        if isinstance(item, tuple):
            top, subs = item
            p = tf.paragraphs[0] if idx == 0 else tf.add_paragraph()
            p.text = top
            p.level = 0
            p.font.size = Pt(22)
            p.font.color.rgb = BODY_COLOR
            p.font.bold = True
            for sub in subs:
                sp = tf.add_paragraph()
                sp.text = sub
                sp.level = 1
                sp.font.size = Pt(18)
                sp.font.color.rgb = BODY_COLOR
        else:
            p = tf.paragraphs[0] if idx == 0 else tf.add_paragraph()
            p.text = item
            p.level = 0
            p.font.size = Pt(21)
            p.font.color.rgb = BODY_COLOR

    if notes:
        slide.notes_slide.notes_text_frame.text = notes


def add_two_col_slide(title, left_title, left_points, right_title, right_points):
    slide = prs.slides.add_slide(prs.slide_layouts[5])
    slide.shapes.title.text = title
    slide.shapes.title.text_frame.paragraphs[0].runs[0].font.color.rgb = TITLE_COLOR
    slide.shapes.title.text_frame.paragraphs[0].runs[0].font.bold = True

    left = slide.shapes.add_textbox(Inches(0.7), Inches(1.5), Inches(5.9), Inches(5.2))
    right = slide.shapes.add_textbox(Inches(6.6), Inches(1.5), Inches(5.9), Inches(5.2))

    for box, box_title, pts in [(left, left_title, left_points), (right, right_title, right_points)]:
        tf = box.text_frame
        tf.text = box_title
        p0 = tf.paragraphs[0]
        p0.font.size = Pt(24)
        p0.font.bold = True
        p0.font.color.rgb = ACCENT
        for point in pts:
            p = tf.add_paragraph()
            p.text = point
            p.level = 0
            p.font.size = Pt(18)
            p.font.color.rgb = BODY_COLOR


add_title_slide(
    "Predictive Page Preloading PoC",
    "Using per-user AI/ML prediction to make page navigation feel instant"
)

add_bullets_slide(
    "Problem & Idea",
    [
        "Web pages feel slow when users repeatedly visit known content paths",
        "Use historical per-user navigation patterns to predict next page",
        "Preload predicted destination before click so navigation appears instant",
        "Keep model + prediction data persistent in MSSQL for reuse across sessions"
    ]
)

add_bullets_slide(
    "Implemented Architecture",
    [
        ("Frontend (Nginx static app)", [
            "Dashboard UI, user management, navigation buttons",
            "rel=\"preload\" links for predicted destination pages"
        ]),
        ("Backend (FastAPI)", [
            "Visit tracking, model training, prediction APIs",
            "Prediction snapshots stored and retrieved from DB"
        ]),
        ("Database (MSSQL)", [
            "Stores users, pages, page visits, trained model payload, snapshots"
        ]),
        ("Runtime", [
            "All services run in Podman containers"
        ])
    ]
)

add_bullets_slide(
    "AI/ML Model Used",
    [
        "Model type: First-order Markov transition model per user",
        "Training input: Ordered sequence of each user's page visits",
        "Output: P(next_page | current_page)",
        "Ranking enhancement: Prioritize by visit_count, then probability",
        "Model payload stored as JSON in table: user_transition_models"
    ]
)

add_two_col_slide(
    "Database Design",
    "Core Tables",
    [
        "users (id, username, created_at)",
        "pages (id, url, title, content)",
        "page_visits (user_id, page_id, visited_at)",
        "user_transition_models (model_type, model_payload, trained_at)",
        "user_prediction_snapshots (current_url, predictions_payload, generated_at)"
    ],
    "Why This Matters",
    [
        "Full audit trail of navigation",
        "Persistent model state per user",
        "Precomputed prediction snapshots",
        "Fast reload of predicted routes",
        "Supports future model upgrades"
    ]
)

add_bullets_slide(
    "Prediction & Preload Flow",
    [
        "1) User selected/created in dashboard",
        "2) Backend loads stored prediction snapshot for current URL",
        "3) Navigate bar is reordered by predicted priority",
        "4) rel=\"preload\" issued for highest-priority destination pages",
        "5) On button click, visit is recorded and model is updated",
        "6) User is redirected to unique page route"
    ]
)

add_bullets_slide(
    "Key API Endpoints",
    [
        "POST /api/users -> create or load user id",
        "GET /api/users -> existing users for dropdown",
        "POST /api/visit -> append visit, retrain model",
        "GET /api/predict-next/{user_id}?current_url=... -> ranked predictions",
        "GET /api/stored-prediction/{user_id}?current_url=... -> snapshot restore",
        "GET /api/history/{user_id} -> journey history"
    ]
)

add_bullets_slide(
    "What Is Persisted Across Sessions",
    [
        "MSSQL named volume retains all user data, models, and snapshots",
        "Predictions survive app refresh and container restart",
        "Active dashboard user can be retained when navigating back",
        "Manual refresh behavior can intentionally clear active user context"
    ]
)

add_bullets_slide(
    "Complexity & Trade-offs",
    [
        "Current approach is lightweight and fast for PoC scale",
        "Model training cost is low (linear over user visit sequence)",
        "Latency mostly from API + DB roundtrips, not model compute",
        "Compared to deep learning, this is simpler and cheaper to operate",
        "Future option: recency-weighted Markov or session-based neural model"
    ]
)

add_bullets_slide(
    "Next Step Opportunities",
    [
        "A/B test: preload vs no-preload perceived speed",
        "Add confidence thresholds before preloading",
        "Track preload hit-rate and wasted preload percentage",
        "Support richer models and feature engineering",
        "Harden for production (auth, metrics, retries, CI tests)"
    ]
)

prs.save(out_path)
print(out_path)
