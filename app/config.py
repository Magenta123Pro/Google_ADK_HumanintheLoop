# Configuration for PeriMeter AI

MODEL_NAME = "gemini-3.1-pro"

# The 6 hormones and their target activities
HORMONE_ACTIVITIES = {
    "Estrogen": {
        "question": "Which activity did you prioritize for Estrogen (Estradiol) support today?",
        "options": [
            {"text": "Strength training or eating cruciferous vegetables", "correct": True},
            {"text": "Deep breathing exercises for 10 minutes", "correct": False},
            {"text": "Going to bed at a consistent time", "correct": False}
        ]
    },
    "Progesterone": {
        "question": "How did you support Progesterone levels today?",
        "options": [
            {"text": "Breathwork/meditation, zinc, or limiting alcohol", "correct": True},
            {"text": "Eating fiber-rich meals first", "correct": False},
            {"text": "Walking 15 minutes after dinner", "correct": False}
        ]
    },
    "Insulin": {
        "question": "What did you do to manage Insulin sensitivity today?",
        "options": [
            {"text": "Fiber-first eating, post-meal walk, or 12-hour rest", "correct": True},
            {"text": "Engaging in morning sunlight exposure", "correct": False},
            {"text": "Drinking green tea instead of coffee in the afternoon", "correct": False}
        ]
    },
    "Cortisol": {
        "question": "How did you maintain a healthy Cortisol rhythm today?",
        "options": [
            {"text": "Caffeine elimination after noon, nature immersion, or stretching", "correct": True},
            {"text": "Eating organic leafy greens", "correct": False},
            {"text": "Consuming magnesium glycinate before sleep", "correct": False}
        ]
    },
    "LH_FSH": {
        "question": "What step did you take for LH and FSH pituitary surge stabilization?",
        "options": [
            {"text": "Adequate calories, consistent sleep, or acupuncture", "correct": True},
            {"text": "Prioritizing daily hydration with filtered water", "correct": False},
            {"text": "Taking a warm bath to unwind", "correct": False}
        ]
    },
    "Melatonin": {
        "question": "How did you support natural Melatonin production today?",
        "options": [
            {"text": "Morning sunlight exposure, blue-light block, or magnesium", "correct": True},
            {"text": "Doing a moderate strength training session", "correct": False},
            {"text": "Eating cruciferous vegetables with lunch", "correct": False}
        ]
    }
}
