export type EvaluationInput = {
  lot_id: string;
  test_run_id: string;
  test_date: string;
  paddy_input_weight: number;
  total_milled_rice_weight: number;
  brown_rice_weight: number | null;
  head_rice_weight: number | null;
  moisture_content: number | null;
  machine_notes: string;
};
export type Evaluation = EvaluationInput & {
  id: number;
  user_id: number;
  total_milling_recovery: number;
  brown_rice_recovery: number | null;
  head_rice_recovery: number | null;
  status: 'awaiting_model';
  created_at: string;
  updated_at: string;
  has_image: boolean;
};
export const percent = (value: number | null | undefined) =>
  value === null || value === undefined ? 'Not measured' : `${value.toFixed(2)}%`;
export const dateDisplay = (value: string) => {
  const parsed = new Date(value.length === 10 ? `${value}T12:00:00` : value);
  return Number.isNaN(parsed.valueOf()) ? value : parsed.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
};
