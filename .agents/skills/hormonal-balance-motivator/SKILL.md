---
name: hormonal-balance-motivator
description: A daily hormonal balance motivator agent designed specifically for perimenopausal women to track daily logs, calculate scores, handle HITL coach reviews, and motivate.
---

# Hormonal Balance Motivator Agent

This agent tracks 6 critical hormones and their correct daily target activities for perimenopausal women.

## Core Workflows

### 1. Eligibility Screening
The agent verifies that the user:
* Is of female biology (`gender == "female"`).
* Is aged 35 or older (`age >= 35`).
* Is experiencing symptoms of perimenopause (`perimenopause_status == "yes"`).
If ineligible, the agent blocks them from accessing the motivator dashboard.

### 2. Custom Hormonal Scoring Rules
For each of the 6 hormones:
* **0 correct activities checked**: +0 points.
* **1 correct activity checked**: +10 points.
* **More than 1 correct activity checked**: +10 points + 3 extra points for each selection under that hormone.
* Incorrect options are removed (no penalties).

### 3. Human-In-The-Loop (HITL) Coaching
* If the total daily score is less than 50, the loop is suspended.
* The session is queued for the Health Coach Portal.
* When the coach approves and adds encouraging comments, the loop is resumed.
* An email alert log is written to `app/email_logs.txt` and a notification is sent.

### 4. Daily Motivation & Joke Generation
* High Score (>= 50): Generates 1 clean, lighthearted self-care joke.
* Low Score (< 50): Generates 2 clean jokes and personalized advice based on missed activities.
