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
  status: 'awaiting_model' | 'screening_trial';
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

/** Count-only experimental visual screening; not a validated grade or DSS result. */
export type ScreeningResult = {
  status: 'experimental_unvalidated_segmentation';
  segmentation_source: 'experimental_opencv_unvalidated';
  model_configuration: string;
  classes: string[];
  total_grains: number;
  counts: Record<string, number>;
  count_percentages: Record<string, number>;
  grains: {grain_index: number; category: string; score: number; bbox_xywh: number[]}[];
  segmentation_warnings: string[];
  manual_verification_required: true;
  measurement_basis: 'grain_count_not_weight';
  dss_result: null;
  official_grade: null;
};
export type ScreeningRecord = {
  status: 'not_requested'|'processing'|'research_preview'|'failed';
  result: ScreeningResult|null;
  error_message?: string|null;
  attempts?: number;
};
export const qualityClassNames: {id:string;title:string}[] = [
  {id:'whole_grain',title:'Whole Grain'},
  {id:'broken_grain',title:'Broken Grain'},
  {id:'chalky_grain',title:'Chalky Grain'},
  {id:'discolored_grain',title:'Discolored Grain'},
];
