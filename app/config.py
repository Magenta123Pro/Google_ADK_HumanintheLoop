# Configuration for PeriMeter AI

MODEL_NAME = "gemini-3.1-pro"

# The 6 hormones and their target activities
HORMONE_ACTIVITIES = {
    "Estrogen": {
        "question": "Which activity did you prioritize for Estrogen (Estradiol) support today?",
        "options": [
            {"text": "Strength training or eating cruciferous vegetables", "correct": True},
            {"text": "Skipping hydration and eating processed foods", "correct": False},
            {"text": "Prolonged sitting without physical movement", "correct": False}
        ]
    },
    "Progesterone": {
        "question": "How did you support Progesterone levels today?",
        "options": [
            {"text": "Breathwork/meditation, zinc, or limiting alcohol", "correct": True},
            {"text": "Drinking late-night wine and staying highly stressed", "correct": False},
            {"text": "Ignoring relaxation and skipping nutrient-dense foods", "correct": False}
        ]
    },
    "Insulin": {
        "question": "What did you do to manage Insulin sensitivity today?",
        "options": [
            {"text": "Fiber-first eating, post-meal walk, or 12-hour rest", "correct": True},
            {"text": "Eating high-carb snacks immediately upon waking up", "correct": False},
            {"text": "Sitting for hours immediately after main meals", "correct": False}
        ]
    },
    "Cortisol": {
        "question": "How did you maintain a healthy Cortisol rhythm today?",
        "options": [
            {"text": "Caffeine elimination after noon, nature immersion, or stretching", "correct": True},
            {"text": "Drinking a double espresso at 4:00 PM", "correct": False},
            {"text": "Engaging in high-intensity stressful screen work late", "correct": False}
        ]
    },
    "LH_FSH": {
        "question": "What step did you take for LH and FSH pituitary surge stabilization?",
        "options": [
            {"text": "Adequate calories, consistent sleep, or acupuncture", "correct": True},
            {"text": "Severe calorie restriction and dynamic sleep times", "correct": False},
            {"text": "Working overnight and skipping regular meals", "correct": False}
        ]
    },
    "Melatonin": {
        "question": "How did you support natural Melatonin production today?",
        "options": [
            {"text": "Morning sunlight exposure, blue-light block, or magnesium", "correct": True},
            {"text": "Using screens in bed without filters until late night", "correct": False},
            {"text": "Staying in a dark room all morning and drinking caffeine late", "correct": False}
        ]
    }
}
