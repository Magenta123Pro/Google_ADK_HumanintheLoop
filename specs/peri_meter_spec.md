# BDD Specification - Peri-Meter AI

## Feature: Hormonal Balance Motivator Agent (Peri-Meter AI)
  As a perimenopausal woman,
  I want to track my daily activities that affect my hormone balance
  So that I can receive feedback, motivation, and healthy suggestions.

  ## Background: Hormones and Correct Target Activities
    The app tracks 6 critical hormones and their correct daily target activities:
    - **Estrogen**: Strength training, Eating cruciferous vegetables, Daily hydration
    - **Progesterone**: Breathwork and meditation, Consuming zinc, Limiting alcohol intake
    - **Insulin**: Fiber-first eating, Walking post-meals, Time-restricted feeding
    - **Cortisol**: Caffeine elimination after noon, Nature immersion, Stretching or Restorative Yoga
    - **LH & FSH**: Adequate caloric intake, Consistent sleep schedule, Acupuncture
    - **Melatonin**: Morning sunlight, Blue-light blocking, Magnesium glycinate

    Scoring Rule:
    - +10 points for each correct activity selected
    - -5 points for each incorrect (but positive wellness) activity selected

  ## Scenario 1: Onboarding with ineligible or invalid details
    Given the onboarding form is presented
    When the user submits any of the following:
      | Name    | Age | Gender | Perimenopause Symptoms |
      | Alice   | 0   | female | yes                    |
      | Bob     | 40  | male   | no                     |
      | Carol   | 30  | female | yes                    |
    Then the app must reject the registration
    And display a friendly message explaining that Peri-Meter AI is designed specifically for women aged 35+ undergoing perimenopause.

  ## Scenario 2: Eligible user with high daily score (>= 50)
    Given the user has completed onboarding successfully
    When they submit their daily activities:
      - Estrogen: "Strength training or eating cruciferous vegetables" (+10)
      - Progesterone: "Breathwork/meditation, zinc, or limiting alcohol" (+10)
      - Insulin: "Fiber-first eating, post-meal walk, or 12-hour rest" (+10)
      - Cortisol: "Caffeine elimination after noon, nature immersion, or stretching" (+10)
      - LH & FSH: "Adequate calories, consistent sleep, or acupuncture" (+10)
      - Melatonin: "Morning sunlight exposure, blue-light block, or magnesium" (+10)
    Then the calculated score should be 60
    And the app should display the score of 60
    And the app should generate and display 1 lighthearted joke to make them smile.

  ## Scenario 3: Eligible user with low daily score (< 50) requiring HITL Coach Review
    Given the user has completed onboarding successfully
    When they submit their daily activities:
      - Estrogen: "Strength training or eating cruciferous vegetables" (+10)
      - Progesterone: "Eating fiber-rich meals first" (-5) (incorrect for Progesterone)
      - Insulin: "Fiber-first eating, post-meal walk, or 12-hour rest" (+10)
      - Cortisol: "Consuming magnesium glycinate before sleep" (-5) (incorrect for Cortisol)
      - LH & FSH: "Adequate calories, consistent sleep, or acupuncture" (+10)
      - Melatonin: "Morning sunlight exposure, blue-light block, or magnesium" (+10)
    Then the calculated score should be 30
    And the agent workflow should suspend and enter "Pending Coach Review" state
    When the Health Coach logs in, reviews the details, and submits a custom motivational note
    Then the session should resume
    And the app should display:
      - The score of 30
      - The coach's custom motivational note
      - 2 jokes to cheer them up
      - Personalized "girl talk" explaining how to balance the missed hormones (Progesterone and Cortisol)
