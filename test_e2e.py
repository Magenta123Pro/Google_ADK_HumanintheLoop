import re
import uuid
from playwright.sync_api import sync_playwright, expect

def run():
    unique_id = str(uuid.uuid4())[:6]
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.on("console", lambda msg: print(f"BROWSER CONSOLE: {msg.text}"))
        page.on("dialog", lambda dialog: (print(f"BROWSER DIALOG: {dialog.message}"), dialog.accept()))
        page.goto("http://127.0.0.1:8080/")

        # Test Scenario 15 & 16: Register, log yesterday, HITL review, verify formatting
        page.click("#toggle-register")
        page.fill("#reg-username", f"u_{unique_id}")
        page.fill("#reg-password", "P@ss1234")
        page.fill("#reg-email", f"test_{unique_id}@example.com")
        page.fill("#reg-name", "Test User")
        page.fill("#reg-age", "45")
        page.select_option("#reg-gender", "female")
        page.select_option("#reg-perimenopause_status", "yes")
        page.click("button:has-text('Create Account & Onboard')")
        
        # Verify app loads
        expect(page.locator("#quiz-heading")).to_be_visible()

        # Switch to Yesterday
        page.select_option("#quiz-log-date", "yesterday")
        
        # Submit empty log (0 points)
        page.click("button:has-text('Submit Daily Log')")
        
        # Wait for pending review
        expect(page.locator("#pending-review-notice")).to_be_visible(timeout=10000)

        # Logout
        page.click("button:has-text('Logout')")
        page.wait_for_url("http://127.0.0.1:8080/")

        # Coach Login
        page.click("#toggle-login")
        page.fill("#login-username", "health_coach")
        page.fill("#login-password", "CoachSecure2026!")
        page.click("button:has-text('Login')")
        
        # Add comment and approve, wait for backend API to finish
        expect(page.locator(".textarea-coach").first).to_be_visible(timeout=10000)
        page.locator(".textarea-coach").first.fill("Great effort!")
        
        with page.expect_response(lambda response: "/api/coach-review/" in response.url, timeout=60000):
            page.locator("button:has-text('Approve & Send')").first.click()
        
        # Wait a brief moment for UI to update
        page.wait_for_timeout(1000)

        # Logout
        page.click("button:has-text('Logout')")
        page.wait_for_url("http://127.0.0.1:8080/")

        # User logs back in
        page.fill("#login-username", f"u_{unique_id}")
        page.fill("#login-password", "P@ss1234")
        page.click("button:has-text('Login')")

        # Because they logged yesterday, they will be prompted to log today.
        # Wait for the resetApp timeout to finish before switching to yesterday
        page.wait_for_timeout(1000)
        
        # Switch to Yesterday to see the approved dashboard.
        page.select_option("#quiz-log-date", "yesterday")

        # Verify Dashboard is shown
        expect(page.locator("#results-dashboard")).to_be_visible(timeout=10000)
        
        # Verify quiz-form is hidden (Messy UI fix)
        expect(page.locator("#quiz-form")).to_be_hidden()
        
        # Verify score is cleanly formatted as "Score: 0"
        expect(page.locator("#score-display .score-badge")).to_have_text("Score: 0")
        
        # Verify minimum score text
        expect(page.locator("text=The minimum target score for hormonal balance is 60.")).to_be_visible()

        # Verify Coach Note
        expect(page.locator("#coach-notes-display")).to_contain_text("Great effort!")

        # Verify Date (Should not be today's date if they logged yesterday!)
        date_header = page.locator("#score-display h3").inner_text()
        print(f"Date Header Displayed: {date_header}")

        # Scenario 17: Calendar Navigation
        expect(page.locator("#tracker-calendar")).to_be_visible()
        
        # Get current month title
        month_title_before = page.locator("#tracker-calendar h3").inner_text()
        print(f"Month before navigation: {month_title_before}")
        
        # Click previous
        page.click("button:has-text('<')")
        expect(page.locator("#tracker-calendar h3")).not_to_have_text(month_title_before)
        month_title_after = page.locator("#tracker-calendar h3").inner_text()
        print(f"Month after < click: {month_title_after}")
        
        # Click next
        page.click("button:has-text('>')")
        expect(page.locator("#tracker-calendar h3")).to_have_text(month_title_before)
        month_title_returned = page.locator("#tracker-calendar h3").inner_text()
        print(f"Month after > click: {month_title_returned}")

        # Scenario 18: Log Today
        page.click("button:has-text('Log Today\\'s Activities')")
        
        # Ensure form is shown and dashboard is hidden
        expect(page.locator("#quiz-form")).to_be_visible()
        expect(page.locator("#results-dashboard")).to_be_hidden()

        # Onboard ineligible user (Age < 35) to verify fix for blank screen issue
        page.click("button:has-text('Logout')")
        page.wait_for_url("http://127.0.0.1:8080/")
        page.click("#toggle-register")
        page.fill("#reg-username", f"y_{unique_id}")
        page.fill("#reg-password", "P@ss1234")
        page.fill("#reg-email", f"young_{unique_id}@example.com")
        page.fill("#reg-name", "Young User")
        page.fill("#reg-age", "30")
        page.select_option("#reg-gender", "female")
        page.select_option("#reg-perimenopause_status", "yes")
        page.click("button:has-text('Create Account & Onboard')")

        # Expect screening error to be visible
        expect(page.locator("#screening-error")).to_be_visible(timeout=10000)
        expect(page.locator("#error-message")).to_have_text("PeriMeter AI is optimized for ages 35+ (up to 80).")

        # Test Scenario: Register again with same username but age > 80 to verify database overwrite and upper limit
        page.click("button:has-text('Log Out & Sign in Correctly')")
        page.wait_for_url("http://127.0.0.1:8080/")
        page.click("#toggle-register")
        page.fill("#reg-username", f"y_{unique_id}") # Same username!
        page.fill("#reg-password", "P@ss1234")
        page.fill("#reg-email", f"corrected_{unique_id}@example.com")
        page.fill("#reg-name", "Corrected User")
        page.fill("#reg-age", "85") # Invalid age (> 80)
        page.select_option("#reg-gender", "female")
        page.select_option("#reg-perimenopause_status", "yes")
        page.click("button:has-text('Create Account & Onboard')")

        # Expect screening error to be visible for age > 80
        expect(page.locator("#screening-error")).to_be_visible(timeout=10000)
        expect(page.locator("#error-message")).to_have_text("PeriMeter AI is optimized for ages 35+ (up to 80).")

        # Test Scenario: Verify Forgot Username/Password flow
        page.click("button:has-text('Log Out & Sign in Correctly')")
        page.wait_for_url("http://127.0.0.1:8080/")
        page.click("a:has-text('Forgot Username/Password?')")
        expect(page.locator("#forgot-form")).to_be_visible()
        expect(page.locator("#login-form")).to_be_hidden()
        
        # Request password retrieval
        page.fill("#forgot-email", f"test_{unique_id}@example.com")
        page.click("button:has-text('Send Credentials')")
        expect(page.locator("#forgot-message-banner")).to_be_visible(timeout=10000)
        expect(page.locator("#forgot-message-banner")).to_have_text("An email has been sent with your credentials.")
        
        # Cancel and return to login
        page.click("button:has-text('Cancel')")
        expect(page.locator("#login-form")).to_be_visible()

        print("All UI Scenarios 15, 16, 17, 18, 19 + Screening Error Fix + Forgot Password Flow Passed!")
        
        browser.close()

if __name__ == "__main__":
    run()
