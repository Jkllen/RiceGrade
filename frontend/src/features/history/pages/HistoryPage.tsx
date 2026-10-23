import { useEffect, useState } from "react";
import {
  Header,
  Icon,
  Notice,
  Busy,
  Empty,
  StatusPill,
} from "../../../components/ui/Elements";
import { AssessmentInsights } from "../../../components/ui/AssessmentInsights";
import { SamplePhotoInput } from "../../../components/ui/SamplePhotoInput";
import { apiRequest, getProtectedImage } from "../../../lib/authApi";
import {
  type Evaluation,
  type ScreeningRecord,
  dateDisplay,
  percent,
} from "../../../lib/evaluations";

type Props = {
  onNew: () => void;
  refresh: number;
  selectedId: number | null;
  clearSelected: () => void;
  onSelect: (id: number) => void;
  onChanged: () => void;
};
export function HistoryPage({
  onNew,
  refresh,
  selectedId,
  clearSelected,
  onSelect,
  onChanged,
}: Props) {
  const [items, setItems] = useState<Evaluation[]>([]);
  const [search, setSearch] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(true);
  const [imageUrl, setImageUrl] = useState("");
  const [imageVersion, setImageVersion] = useState(0);
  const [deleteBusy, setDeleteBusy] = useState(false);
  const [uploadBusy, setUploadBusy] = useState(false);
  const [screening, setScreening] = useState<ScreeningRecord | null>(null);
  const [screeningBusy, setScreeningBusy] = useState(false);
  const selected = items.find((item) => item.id === selectedId);
  useEffect(() => {
    let live = true;
    setBusy(true);
    apiRequest<Evaluation[]>("/evaluations")
      .then((rows) => {
        if (live) {
          setItems(rows);
          setError("");
        }
      })
      .catch((e) => {
        if (live) setError(e.message);
      })
      .finally(() => {
        if (live) setBusy(false);
      });
    return () => {
      live = false;
    };
  }, [refresh]);
  useEffect(() => {
    let live = true;
    let image = "";
    setImageUrl("");
    if (selected?.has_image) {
      getProtectedImage(selected.id)
        .then((url) => {
          if (live) {
            image = url;
            setImageUrl(url);
          } else URL.revokeObjectURL(url);
        })
        .catch(() => {});
    }
    return () => {
      live = false;
      if (image) URL.revokeObjectURL(image);
    };
  }, [selected?.id, selected?.has_image, imageVersion]);
  useEffect(() => {
    let live = true;
    setScreening(null);
    if (selectedId !== null) {
      apiRequest<ScreeningRecord>(`/evaluations/${selectedId}/screening`)
        .then((r) => {
          if (live) setScreening(r);
        })
        .catch(() => {});
    }
    return () => {
      live = false;
    };
  }, [selectedId, refresh]);
  async function runScreening() {
    if (!selected?.has_image) return;
    setScreeningBusy(true);
    setError("");
    try {
      const rec = await apiRequest<ScreeningRecord>(
        `/evaluations/${selected.id}/screening`,
        { method: "POST" },
      );
      setScreening(rec);
      onChanged();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Analysis could not complete");
      try {
        setScreening(
          await apiRequest<ScreeningRecord>(
            `/evaluations/${selected.id}/screening`,
          ),
        );
      } catch {
        /* keep result */
      }
    } finally {
      setScreeningBusy(false);
    }
  }
  async function remove() {
    if (
      !selected ||
      !window.confirm(`Delete ${selected.test_run_id}? This cannot be undone.`)
    )
      return;
    setDeleteBusy(true);
    try {
      await apiRequest(`/evaluations/${selected.id}`, { method: "DELETE" });
      clearSelected();
      onChanged();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unable to delete assessment");
    } finally {
      setDeleteBusy(false);
    }
  }
  async function replaceImage(file: File | undefined) {
    if (!selected || !file) return;
    setUploadBusy(true);
    setError("");
    try {
      const data = new FormData();
      data.append("image", file);
      await apiRequest(`/evaluations/${selected.id}/image`, {
        method: "POST",
        body: data,
      });
      setScreening(null);
      setImageVersion((v) => v + 1);
      onChanged();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unable to upload image");
    } finally {
      setUploadBusy(false);
    }
  }
  const visible = items.filter((i) =>
    `${i.lot_id} ${i.test_run_id} ${i.test_date}`
      .toLowerCase()
      .includes(search.toLowerCase()),
  );
  const hasResult =
    screening?.status === "research_preview" && Boolean(screening.result);
  return (
    <>
      <Header
        eyebrow="YOUR RECORDS"
        title="Assessment history"
        description="Find past test runs, reopen annotated results, and manage your saved records."
        actions={
          <button className="button button-primary" onClick={onNew}>
            <Icon name="analysis" size={17} />
            New evaluation
          </button>
        }
      />
      {error && <Notice tone="warning">{error}</Notice>}
      {selected ? (
        <section className="panel detail-panel">
          <button className="text-button back-link" onClick={clearSelected}>
            ← Back to history
          </button>
          <div className="detail-heading">
            <div>
              <p className="eyebrow">TEST RUN {selected.id}</p>
              <h2>{selected.lot_id}</h2>
              <p>
                {selected.test_run_id} · {dateDisplay(selected.test_date)}
              </p>
            </div>
            <StatusPill>{hasResult ? "Analyzed" : "Saved"}</StatusPill>
          </div>
          <div className="detail-ops">
            <h3>
              {hasResult ? "Analysis & recommendations" : "Sample analysis"}
            </h3>
            {!hasResult && selected.has_image && (
              <div className="button-row">
                <button
                  className="button button-primary"
                  onClick={() => void runScreening()}
                  disabled={
                    screeningBusy ||
                    screening?.status === "processing" ||
                    (screening?.attempts ?? 0) >= 3
                  }
                >
                  {screeningBusy
                    ? "Analyzing grains…"
                    : screening?.status === "processing"
                      ? "Analysis in progress"
                      : "Analyze Grain Screen"}{" "}
                  <Icon name="arrow" size={17} />
                </button>
              </div>
            )}
          </div>
          {screening?.status === "failed" && (
            <Notice tone="warning">
              {screening.error_message ||
                "Image analysis could not finish. Check the image and service connection."}
            </Notice>
          )}
          {selected.has_image && !imageUrl && (
            <Busy label="Loading sample image…" />
          )}
          <AssessmentInsights
            evaluation={selected}
            result={hasResult ? screening!.result : null}
            imageUrl={imageUrl || undefined}
          />
          <div className="detail-bottom">
            <div>
              <h3>Sample photo</h3>
              <p>
                Replacing an image clears its previous analysis, allowing a new
                screening attempt.
              </p>
              <SamplePhotoInput
                busy={uploadBusy || screeningBusy}
                disabled={screeningBusy}
                onPhoto={(file) => replaceImage(file)}
                title={selected.has_image ? "Replace photo" : "Attach a photo"}
              />
            </div>
            <div>
              <h3>Recorded measurements</h3>
              <div className="detail-grid">
                <div>
                  <span>Paddy input</span>
                  <strong>{selected.paddy_input_weight} g</strong>
                </div>
                <div>
                  <span>Total milled rice</span>
                  <strong>{selected.total_milled_rice_weight} g</strong>
                </div>
                <div>
                  <span>Head rice</span>
                  <strong>
                    {selected.head_rice_weight == null
                      ? "Not measured"
                      : `${selected.head_rice_weight} g`}
                  </strong>
                </div>
                <div>
                  <span>Created on</span>
                  <strong>{dateDisplay(selected.created_at)}</strong>
                </div>
              </div>
            </div>
          </div>
          {selected.machine_notes && (
            <div className="record-note">
              <strong>Operator notes</strong>
              <p>{selected.machine_notes}</p>
            </div>
          )}
          <div className="button-row">
            <button
              className="button button-danger"
              disabled={deleteBusy}
              onClick={() => void remove()}
            >
              {deleteBusy ? "Deleting…" : "Delete assessment"}
            </button>
            <button className="button button-secondary" onClick={clearSelected}>
              Back to history
            </button>
          </div>
        </section>
      ) : (
        <section className="panel history-panel">
          <div className="list-toolbar">
            <label className="search-field">
              <Icon name="search" size={19} />
              <input
                aria-label="Search assessments"
                placeholder="Search lot or test-run ID"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
              />
            </label>
            <span className="count-label">
              {visible.length} record{visible.length !== 1 ? "s" : ""}
            </span>
          </div>
          {busy ? (
            <Busy />
          ) : visible.length ? (
            <div className="record-list">
              {visible.map((i) => (
                <button
                  key={i.id}
                  className="record-row"
                  onClick={() => onSelect(i.id)}
                >
                  <div className="record-badge">
                    <Icon name="analysis" />
                  </div>
                  <div className="record-main">
                    <strong>
                      {i.lot_id}{" "}
                      <span className="subtle">/ {i.test_run_id}</span>
                    </strong>
                    <span>
                      {dateDisplay(i.test_date)} · Total recovery{" "}
                      {percent(i.total_milling_recovery)}{" "}
                      {i.has_image ? "· Photo attached" : ""}
                    </span>
                  </div>
                  <StatusPill>
                    {i.status === "screening_trial" ? "Analyzed" : "Saved"}
                  </StatusPill>
                  <Icon name="arrow" size={18} />
                </button>
              ))}
            </div>
          ) : (
            <Empty
              icon="history"
              title={search ? "No matching records" : "No assessments yet"}
              description={
                search
                  ? "Try another lot or test-run ID."
                  : "Your completed test runs will appear here."
              }
            >
              {!search && (
                <button className="button button-primary" onClick={onNew}>
                  Start an evaluation
                </button>
              )}
            </Empty>
          )}
        </section>
      )}
    </>
  );
}
