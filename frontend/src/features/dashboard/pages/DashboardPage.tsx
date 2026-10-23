import { useEffect, useState } from "react";
import { type ScreenKey } from "../../../components/layout/AppShell";
import {
  Header,
  Icon,
  Notice,
  Busy,
  StatusPill,
} from "../../../components/ui/Elements";
import { apiRequest, type User } from "../../../lib/authApi";
import {
  type Evaluation,
  dateDisplay,
  percent,
} from "../../../lib/evaluations";

type Props = {
  onNavigate: (screen: ScreenKey) => void;
  onLogout: () => void;
  user: User;
  refresh: number;
  onSelect: (id: number) => void;
};
export function DashboardPage({
  onNavigate,
  onLogout,
  user,
  refresh,
  onSelect,
}: Props) {
  const [items, setItems] = useState<Evaluation[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    setLoading(true);
    apiRequest<Evaluation[]>("/evaluations")
      .then((data) => {
        if (active) {
          setItems(data);
          setError("");
        }
      })
      .catch((e) => {
        if (active) setError(e.message);
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [refresh]);
  // Dashboard actions deliberately mirror the decision branches in the thesis flowchart.
  // History remains a separate archive; newly created evaluations are analyzed immediately.
  const cards: { key: ScreenKey; title: string; copy: string; icon: string }[] =
    [
      {
        key: "analysis",
        title: "Test-Mill Evaluation",
        copy: "Enter measurements, attach a grain photo, and analyze it in one flow.",
        icon: "analysis",
      },
      {
        key: "reports",
        title: "Test-Mill Evaluation Report",
        copy: "Review saved quality results, recovery measurements and DSS guidance.",
        icon: "reports",
      },
      {
        key: "history",
        title: "Assessment History",
        copy: "Search previous test runs, reopen grain overlays and review past results.",
        icon: "history",
      },
      {
        key: "profile",
        title: "Profile Management",
        copy: "Review account details, update your profile and change your password.",
        icon: "profile",
      },
      {
        key: "about",
        title: "About RiceGrade",
        copy: "Learn what the platform measures and how its screening workflow works.",
        icon: "about",
      },
    ];
  return (
    <>
      <Header
        eyebrow="OVERVIEW"
        title={`Good to see you, ${user.full_name.split(" ")[0] || "there"}.`}
        description="Your test-milling workspace, organized in one place."
        actions={
          <button
            className="button button-primary"
            onClick={() => onNavigate("analysis")}
          >
            <Icon name="analysis" size={18} />
            New evaluation
          </button>
        }
      />

      {error && <Notice tone="warning">{error}</Notice>}
      <section className="stats-grid" aria-label="Assessment summary">
        <div className="stat-card">
          <span>Total test runs</span>
          <strong>{loading ? "—" : items.length}</strong>
          <small>Saved assessments</small>
        </div>
        <div className="stat-card">
          <span>Awaiting analysis</span>
          <strong>
            {loading
              ? "—"
              : items.filter((i) => i.status === "awaiting_model").length}
          </strong>
          <small>Earlier incomplete records</small>
        </div>
        <div className="stat-card">
          <span>Analyzed samples</span>
          <strong>
            {loading
              ? "—"
              : items.filter((i) => i.status === "screening_trial").length}
          </strong>
          <small>Visual analysis completed</small>
        </div>
      </section>
      <div className="section-header">
        <div>
          <h2>Quick actions</h2>
          <p>Choose what you want to work on.</p>
        </div>
      </div>
      <div className="quick-grid">
        {cards.map((card) => (
          <button
            key={card.key}
            className="quick-card"
            onClick={() => onNavigate(card.key)}
          >
            <span className="quick-icon">
              <Icon name={card.icon} size={24} />
            </span>
            <strong>{card.title}</strong>
            <span>{card.copy}</span>
            <span className="quick-more">
              Open <Icon name="arrow" size={16} />
            </span>
          </button>
        ))}
        <button type="button" className="quick-card" onClick={onLogout}>
          <span className="quick-icon">
            <Icon name="logout" size={24} />
          </span>
          <strong>Sign Out</strong>
          <span>End your current session securely.</span>
          <span className="quick-more">
            Sign out <Icon name="arrow" size={16} />
          </span>
        </button>
      </div>
      <section className="panel recent-panel">
        <div className="section-header">
          <div>
            <h2>Recent test runs</h2>
            <p>Your latest saved assessments.</p>
          </div>
          <button className="text-button" onClick={() => onNavigate("history")}>
            View all <Icon name="arrow" size={15} />
          </button>
        </div>
        {loading ? (
          <Busy />
        ) : items.length ? (
          <div className="record-list">
            {items.slice(0, 4).map((item) => (
              <button
                className="record-row"
                key={item.id}
                onClick={() => onSelect(item.id)}
              >
                <div className="record-badge">
                  <Icon name="chart" />
                </div>
                <div className="record-main">
                  <strong>
                    {item.lot_id}{" "}
                    <span className="subtle">/ {item.test_run_id}</span>
                  </strong>
                  <span>
                    {dateDisplay(item.test_date)} · Total recovery{" "}
                    {percent(item.total_milling_recovery)}
                  </span>
                </div>
                <StatusPill>
                  {item.status === "screening_trial" ? "Analyzed" : "Saved"}
                </StatusPill>
                <Icon name="arrow" size={18} />
              </button>
            ))}
          </div>
        ) : (
          <div className="compact-empty">
            No test runs yet.{" "}
            <button
              className="text-button"
              onClick={() => onNavigate("analysis")}
            >
              Create your first evaluation
            </button>
            .
          </div>
        )}
      </section>
    </>
  );
}
