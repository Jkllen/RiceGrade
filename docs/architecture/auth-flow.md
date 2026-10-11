# Authentication and navigation — UI-first milestone

- Public account screens: Sign In, Sign Up, Forgot Password and Reset Password.
- Sign-up records full name, email, user type (operator / QA/QC), and a salted PBKDF2 password hash. These role values are descriptive only; they do not grant elevated administrative access.
- Sign-in creates a revocable opaque session (12 hours) with a token digest stored in SQLite. The token is held in the browser's `sessionStorage`; reloading a tab validates it with `GET /api/auth/me`.
- Authenticated users reach the Dashboard. No token or an expired/invalid token shows Sign In. Backend endpoints independently verify the session and row ownership.
- Main navigation: Test-Mill Evaluation, Evaluation Reports, Assessment History, My Profile and Sign Out. Mobile uses a compact bottom navigation plus a slide-in sidebar.
- Profile editing and change password work. Password change requires the old password and signs out other sessions.
- Forgot-password creates a one-time, expiring (30-minute) token and sends an email **only when SMTP is configured**. Unknown emails produce the same outward response as known emails; links become invalid after use. With no SMTP configured, the endpoint clearly returns 503 instead of falsely confirming delivery.
- User records and test-mill assessments are stored in local SQLite. New assessment images belong to the authenticated user, who can also delete their own records.
- Model results are not available until segmentation, feature fusion, and final classifier inference are validated. The interface shows an `awaiting_model` status rather than fake predictions.

## Security and deployment follow-ups

A multi-user production launch still requires HTTPS, WAF and appropriate rate limits (especially login/sign-up/reset endpoints), persistent database storage and backups, secret management, and security review. `sessionStorage` tokens are exposed to any malicious JavaScript running on the origin; CSP helps reduce risk, and HTTP-only secure cookie sessions with CSRF mitigation are a possible future hardening step. There is no verified email-domain ownership step, invitation policy, or privileged admin role in this prototype.
