import { useState, type FormEvent } from "react";
import { Header, Icon, Notice } from "../../../components/ui/Elements";
import { apiRequest, type User } from "../../../lib/authApi";
type Props = { user: User; onUpdated: (user: User) => void };
export function ProfilePage({ user, onUpdated }: Props) {
  const [fullName, setFullName] = useState(user.full_name);
  const [role, setRole] = useState(user.role);
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [profileMessage, setProfileMessage] = useState("");
  const [profileError, setProfileError] = useState("");
  const [passwordMessage, setPasswordMessage] = useState("");
  const [passwordError, setPasswordError] = useState("");
  const [busy, setBusy] = useState(false);
  async function saveProfile(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setProfileError("");
    setProfileMessage("");
    try {
      const saved = await apiRequest<User>("/auth/profile", {
        method: "PATCH",
        body: JSON.stringify({ full_name: fullName, role }),
      });
      onUpdated(saved);
      setProfileMessage("Your profile was updated successfully.");
    } catch (err) {
      setProfileError(
        err instanceof Error ? err.message : "Unable to update profile",
      );
    } finally {
      setBusy(false);
    }
  }
  async function savePassword(e: FormEvent) {
    e.preventDefault();
    setPasswordError("");
    setPasswordMessage("");
    if (newPassword !== confirmPassword) {
      setPasswordError("New passwords do not match");
      return;
    }
    setBusy(true);
    try {
      const r = await apiRequest<{ message: string }>("/auth/change-password", {
        method: "POST",
        body: JSON.stringify({
          current_password: currentPassword,
          new_password: newPassword,
        }),
      });
      setPasswordMessage(r.message);
      setCurrentPassword("");
      setNewPassword("");
      setConfirmPassword("");
    } catch (err) {
      setPasswordError(
        err instanceof Error ? err.message : "Unable to change password",
      );
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <Header
        eyebrow="ACCOUNT SETTINGS"
        title="My profile"
        description="Manage your account information and password."
      />
      <div className="profile-overview panel">
        <span className="avatar profile-avatar">
          {user.full_name.charAt(0).toUpperCase() || "R"}
        </span>
        <div>
          <h2>{user.full_name}</h2>
          <p>{user.email}</p>
          <span className="small-tag">
            {user.role === "qa" ? "QA/QC Personnel" : "Milling Operator"}
          </span>
        </div>
      </div>
      <div className="profile-grid">
        <section className="panel form-section">
          <div className="form-section-title">
            <span className="quick-icon">
              <Icon name="profile" size={22} />
            </span>
            <div>
              <h2>Personal information</h2>
              <p>Update your display name and account type.</p>
            </div>
          </div>
          <form onSubmit={saveProfile} className="form-stack">
            <label className="field">
              Full name
              <input
                minLength={2}
                maxLength={120}
                required
                autoComplete="name"
                value={fullName}
                onChange={(e) => setFullName(e.target.value)}
              />
            </label>
            <label className="field">
              Email address
              <input value={user.email} readOnly disabled />
              <small>Account email cannot be changed in this version.</small>
            </label>
            <label className="field">
              Account type
              <select
                value={role}
                onChange={(e) => setRole(e.target.value as User["role"])}
              >
                <option value="operator">Milling Operator</option>
                <option value="qa">QA/QC Personnel</option>
              </select>
            </label>
            {profileError && <Notice tone="warning">{profileError}</Notice>}
            {profileMessage && <Notice tone="success">{profileMessage}</Notice>}
            <button
              disabled={busy}
              className="button button-primary"
              type="submit"
            >
              Save changes
            </button>
          </form>
        </section>
        <section className="panel form-section">
          <div className="form-section-title">
            <span className="quick-icon">
              <Icon name="lock" size={22} />
            </span>
            <div>
              <h2>Change password</h2>
              <p>Other signed-in devices will be logged out.</p>
            </div>
          </div>
          <form onSubmit={savePassword} className="form-stack">
            <label className="field">
              Current password
              <input
                type="password"
                autoComplete="current-password"
                required
                value={currentPassword}
                onChange={(e) => setCurrentPassword(e.target.value)}
              />
            </label>
            <label className="field">
              New password
              <input
                type="password"
                autoComplete="new-password"
                minLength={12}
                required
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
              />
              <small>At least 12 characters.</small>
            </label>
            <label className="field">
              Confirm new password
              <input
                type="password"
                autoComplete="new-password"
                minLength={12}
                required
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
              />
            </label>
            {passwordError && <Notice tone="warning">{passwordError}</Notice>}
            {passwordMessage && (
              <Notice tone="success">{passwordMessage}</Notice>
            )}
            <button
              disabled={busy}
              className="button button-secondary"
              type="submit"
            >
              Update password
            </button>
          </form>
        </section>
      </div>
    </>
  );
}
