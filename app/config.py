# Configuration for PeriMeter AI

MODEL_NAME = "gemini-3.1-pro"

# The 6 hormones and their target activities
HORMONE_ACTIVITIES = {
    "Estrogen": {
        "question": "Which activity did you prioritize for Estrogen (Estradiol) support today?",
        "options": [
            {"text": "Strength training", "correct": True},
            {"text": "Eating cruciferous vegetables", "correct": True},
            {"text": "Daily hydration", "correct": True}
        ]
    },
    "Progesterone": {
        "question": "How did you support Progesterone levels today?",
        "options": [
            {"text": "Breathwork and meditation", "correct": True},
            {"text": "Consuming zinc", "correct": True},
            {"text": "Limiting alcohol intake", "correct": True}
        ]
    },
    "Insulin": {
        "question": "What did you do to manage Insulin sensitivity today?",
        "options": [
            {"text": "Fiber-first eating", "correct": True},
            {"text": "Walking post-meals", "correct": True},
            {"text": "Time-restricted feeding", "correct": True}
        ]
    },
    "Cortisol": {
        "question": "How did you maintain a healthy Cortisol rhythm today?",
        "options": [
            {"text": "Caffeine elimination after noon", "correct": True},
            {"text": "Nature immersion", "correct": True},
            {"text": "Stretching or Restorative Yoga", "correct": True}
        ]
    },
    "LH_FSH": {
        "question": "What step did you take for LH and FSH pituitary surge stabilization?",
        "options": [
            {"text": "Adequate caloric intake", "correct": True},
            {"text": "Consistent sleep schedule", "correct": True},
            {"text": "Acupuncture", "correct": True}
        ]
    },
    "Melatonin": {
        "question": "How did you support natural Melatonin production today?",
        "options": [
            {"text": "Morning sunlight", "correct": True},
            {"text": "Blue-light blocking", "correct": True},
            {"text": "Magnesium glycinate", "correct": True}
        ]
    }
}
