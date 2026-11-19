// Shared API types (mirror the backend responses).

export type Level = "SICHER" | "PRÜFEN" | "UNSICHER";

export interface User {
  id: number;
  email: string;
  display_name: string;
  is_demo: boolean;
  setup_step: number;
  setup_done: boolean;
  setup_skipped: number[];
  settings: {
    call_names?: string[];
    keep_audio?: boolean;
    consent_reminder?: boolean;
    answer_mode?: "short" | "detailed";
    large_type?: boolean;
    theme?: string;
    models?: Record<string, string>;
    quotas?: Record<string, Record<string, number>>;
  };
}

export interface Module {
  id: number;
  name: string;
  short: string;
  color: string;
  lecturer: string;
  aliases: string[];
  exam_date: string | null;
  exam_mode: boolean;
  retention_days: number | null;
  ects: number;
  moodle_course_id: number | null;
  archived: boolean;
  due_cards?: number;
  exam_in_days?: number | null;
}

export interface Source {
  type: "material" | "statute";
  label: string;
  excerpt: string;
  title?: string;
  document_id?: number;
  page?: number | null;
  start_s?: number | null;
  recording_id?: number | null;
  kind?: string;
  law?: string;
  norm?: string;
  url?: string;
  demo?: boolean;
  sid?: string;
  chunk_id?: number;
}

export interface AnswerT {
  id: number;
  group_id: string;
  question: string;
  reading: string;
  probability: number;
  short: string;
  detailed: string;
  level: Level;
  percent: number;
  why: string;
  sources: Source[];
  engine: string;
  at_s: number | null;
  trigger: string;
  correction: { statement: string; reason: string; corrected: string; at_s: number } | null;
  feedback: string;
  module_id: number | null;
  recording_id: number | null;
  created_at: string | null;
}

export interface Recording {
  id: number;
  title: string;
  module_id: number | null;
  module: string | null;
  module_short: string | null;
  color: string | null;
  lecture_id: number | null;
  started_at: string;
  ended_at: string | null;
  duration_s: number;
  status: string;
  source: string;
  live_answers: boolean;
  answer_mode: "short" | "detailed";
  exam_mode: boolean;
  package_status: string;
  participation: { kind: string; text: string; at_s: number }[];
  context: { statute: { label: string } | null; topic: string[]; slide: SlideRef | null };
}

export interface SlideRef {
  document_id: number;
  page: number | null;
  title: string;
  label: string;
  excerpt: string;
  score: number;
}

export interface Segment {
  id: number;
  start_s: number;
  end_s: number;
  text: string;
  flags: string[];
}

export interface Doc {
  id: number;
  title: string;
  original_name: string;
  kind: string;
  module_id: number | null;
  lecture_id: number | null;
  recording_id: number | null;
  mime: string;
  size: number;
  pages: number;
  status: string;
  status_detail: string;
  source: string;
  doc_date: string | null;
  confidence: number;
  needs_review: boolean;
  review_reason: string;
  version: number;
  meta: Record<string, unknown>;
  created_at: string | null;
}

export interface LiveEvent {
  id: number;
  kind: string;
  payload: Record<string, unknown>;
  at: string;
}

export interface Deadline {
  id: number;
  title: string;
  due: string;
  module_id: number | null;
  source: string;
  status: string;
}

export interface Job {
  id: number;
  kind: string;
  label: string;
  status: string;
  progress: number;
  error: string;
  batch: string;
}
