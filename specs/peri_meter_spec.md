# BDD Specification - PeriMeter AI

## Feature: Hormonal Balance Motivator Agent (PeriMeter AI)
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
    - -5 points for each incorrect/unhealthy activity selected

  ## Scenario 1: Onboarding with ineligible or invalid details
    Given the onboarding form is presented
    When the user submits any of the following:
      | Name    | Age | Gender | Perimenopause Symptoms |
      | Alice   | 0   | female | yes                    |
      | Bob     | 40  | male   | no                     |
      | Carol   | 30  | female | yes                    |
    Then the app must reject the registration
    And display a friendly message explaining that PeriMeter AI is designed specifically for women aged 35+ undergoing perimenopause.

  ## Scenario 2: Eligible user with high daily score (>= 50)
    Given the user has completed onboarding successfully
    When they submit their daily activities:
      - Estrogen: "Strength training" (+10)
      - Progesterone: "Breathwork and meditation" (+10)
      - Insulin: "Fiber-first eating" (+10)
      - Cortisol: "Nature immersion" (+10)
      - LH & FSH: "Adequate caloric intake" (+10)
      - Melatonin: "Blue-light blocking" (+10)
    Then the calculated score should be 60
    And the app should display the score of 60
    And the app should generate and display 1 lighthearted joke to make them smile.

  ## Scenario 3: Eligible user with low daily score (< 50) requiring HITL Coach Review
    Given the user has completed onboarding successfully
    When they submit their daily activities:
      - Estrogen: "Strength training" (+10)
      - Progesterone: "Drinking excessive alcohol" (-5)
      - Insulin: "Fiber-first eating" (+10)
      - Cortisol: "Drinking late afternoon coffee" (-5)
      - LH & FSH: "Adequate caloric intake" (+10)
      - Melatonin: "Magnesium glycinate" (+10)
    Then the calculated score should be 30
    And the agent workflow should suspend and enter "Pending Coach Review" state
    When the Health Coach logs in, reviews the details, and submits a custom motivational note
    Then the session should resume
    And the app should display:
      - The score of 30
      - The coach's custom motivational note
      - 2 jokes to cheer them up
      - Personalized "girl talk" explaining how to balance the missed hormones (Progesterone and Cortisol)
