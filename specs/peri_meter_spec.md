# BDD Specification - Peri-Meter AI

## Feature: Hormonal Balance Motivator Agent (Peri-Meter AI)
  As a perimenopausal woman,
  I want to track my daily activities that affect my hormone balance
  So that I can receive feedback, motivation, and healthy suggestions.

  ## Background: Hormones and Correct Target Activities
    The app tracks 6 critical hormones and their correct daily target activities (only positive correct options are provided):
    - **Estrogen**: Strength training, Eating cruciferous vegetables, Daily hydration
    - **Progesterone**: Breathwork and meditation, Consuming zinc, Limiting alcohol intake
    - **Insulin**: Fiber-first eating, Walking post-meals, Time-restricted feeding
    - **Cortisol**: Caffeine elimination after noon, Nature immersion, Stretching or Restorative Yoga
    - **LH & FSH**: Adequate caloric intake, Consistent sleep schedule, Acupuncture
    - **Melatonin**: Morning sunlight, Blue-light blocking, Magnesium glycinate

    Scoring Rule:
    - If 1 option is selected under a hormone: +10 points
    - If more than 1 option is selected under a hormone: +10 points + 3 extra points for each selection under that hormone

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
      - Estrogen: "Strength training" (+10)
      - Progesterone: "Breathwork and meditation" (+10)
      - Insulin: "Fiber-first eating" (+10)
      - Cortisol: "Caffeine elimination after noon" (+10)
      - LH & FSH: "Adequate caloric intake" (+10)
      - Melatonin: "Morning sunlight" (+10)
    Then the calculated score should be 60
    And the app should display the score of 60
    And the app should generate and display 1 lighthearted joke to make them smile.

  ## Scenario 3: Eligible user with low daily score (< 50) requiring HITL Coach Review
    Given the user has completed onboarding successfully
    When they submit their daily activities:
      - Estrogen: "Strength training" (+10)
      - Progesterone: no option selected (0)
      - Insulin: "Fiber-first eating" (+10)
      - Cortisol: no option selected (0)
      - LH & FSH: "Adequate caloric intake" (+10)
      - Melatonin: "Morning sunlight" (+10)
    Then the calculated score should be 40
    And the agent workflow should suspend and enter "Pending Coach Review" state
    When the Health Coach logs in, reviews the details, and submits a custom motivational note
    Then the session should resume
    And the app should display:
      - The score of 40
      - The coach's custom motivational note
      - 2 jokes to cheer them up
      - Personalized "girl talk" explaining how to balance the missed hormones (Progesterone and Cortisol)

  ## Scenario 4: User registers with age <= 0
    Given a registration form is presented
    When the user enters age <= 0
    Then the app must reject registration with "Age must be a positive number"

  ## Scenario 5: User registers with non-numeric age
    When the user enters a non-numeric string for age
    Then the app must reject registration with "Age must be a positive number"

  ## Scenario 6: User registers with age < 35 (Ineligible screening)
    When the user enters age 34 and female biology and symptoms yes
    Then the registration/login completes
    And the user is immediately screened out with "optimized for ages 35+" and blocked from the daily log

  ## Scenario 7: User registers with gender Male (Ineligible screening)
    When the user enters gender "Male" and age 40 and symptoms yes
    Then the user is immediately screened out with "female biology" warning and blocked

  ## Scenario 8: User registers with symptoms No (Ineligible screening)
    When the user enters symptoms "No" and age 40 and gender female
    Then the user is immediately screened out with "experiencing perimenopause" warning and blocked

  ## Scenario 9: User submits registration with empty required fields
    When the user submits an empty username, password, or name
    Then the app rejects with corresponding field empty validation error

  ## Scenario 10: User submits registration with invalid email
    When the user submits an email without "@" or "."
    Then the app rejects with "Please enter a valid email address"

  ## Scenario 11: User registers with duplicate username
    Given a user already exists in the database
    When a new registration is submitted with the same username
    Then the backend rejects with "Username already exists"

  ## Scenario 12: User logs in with invalid credentials
    When a login is submitted with wrong username or password
    Then the login fails with "Invalid username or password"

  ## Scenario 13: Unauthorized access to Health Coach Portal
    When a non-coach user attempts to call "/api/pending" or "/api/coach-review"
    Then the system returns a 403 Forbidden status

  ## Scenario 14: Submitting empty daily activity log
    When an eligible user logs in and submits a log without selecting any activities
    Then the score is calculated as 0 and the UI enters the "pending Coach review" state

  ## Scenario 15: User logs in after receiving coach alert email (Same Day)
    Given the user's score was under 50 and the Health Coach has submitted a review
    And the user receives the "Your Peri-Meter AI Health Coach Review is Ready!" email
    When the user logs back into the app on the same day
    Then the user immediately sees the results dashboard
    And the dashboard displays their score, Girl Talk, and the specific Coach Encouragement Note

  ## Scenario 16: User logs in after receiving coach alert email (Next Day)
    Given the Health Coach submitted a review for yesterday's log
    When the user logs into the app today
    Then the user sees the calendar view
    When the user clicks on yesterday's date in the calendar
    Then the dashboard opens displaying yesterday's score and the Coach Encouragement Note

  ## Scenario 17: User attempts to resubmit log after viewing coach comments
    Given the user has logged in and viewed their reviewed dashboard for a specific date
    When the user attempts to find or resubmit the quiz form for that same date
    Then the app enforces the one-log-per-date rule
    And the quiz form remains completely hidden, preventing duplicate submissions

  ## Scenario 18: User logs in to view comments but session is expired
    Given the user receives the coach alert email
    When the user clicks the link to open the app but their authentication session has expired
    Then the user is prompted to log in again
    And upon successful login, they can successfully access the dashboard to view the coach note

  ## Scenario 19: User transitions to new daily log after viewing past coach comments
    Given the user logged in and viewed the Health Coach comments for yesterday's log
    When the user clicks "Log Today's Activities"
    Then the app clears the results dashboard
    And the app presents a fresh, empty daily log form targeted for "Today"

