# Authentication and navigation — approved scaffold

- No valid session: public **Sign In**, **Sign Up**, **Forgot Password** screens.
- Sign-up creates an account; sign-in creates a 12-hour opaque session, with token hashes stored in SQLite. Passwords use PBKDF2-HMAC-SHA256 with unique random salts.
- A stored session is verified using `GET /api/auth/me` before dashboard rendering. Signed-in users go to Dashboard; no valid session returns to Sign In.
- Dashboard options: New Rice Analysis, Screening Report, Assessment History, Profile Management and Log Out.
- New Rice Analysis will contain lot/sample registration, physical measurement entry, standardized capture and visual analysis; those operations remain placeholders.
- Protected API routes independently check bearer session tokens; frontend screen hiding is not security.
- Forgot/reset password pages are placeholders. API deliberately returns 501 until email delivery, rate limiting, reset tokens and a safe user-enumeration policy are approved.
- Prototype token storage uses `sessionStorage`, which is vulnerable to XSS. For deployed multi-user access, reassess HTTP-only secure cookies, CSRF defenses, HTTPS, rate limits, operational key management, logging and SQLite write contention.
- No role model, registration invitation policy or email verification has been approved. For now, sign-up is open and users have only their own session identity; sample/report endpoints must enforce ownership when implemented.
- Authentication is an implementation decision, not an empirically validated claim about the ML system.
