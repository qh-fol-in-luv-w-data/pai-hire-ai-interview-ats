export type User = { id?: string; name: string; email?: string; phone?: string; role?: string };
export type Job = { id: string; title: string; category?: string; category_slug?: string; salary_range?: string; location?: string; work_type?: string; logo_url?: string; jd_content?: string; level?: string; is_active?: boolean };
export type Application = {
  id: string; job_id: string; name: string; email: string; phone?: string; cv_path?: string; cv_score?: number | null;
  application_source?: string;
  status: string; applied_at: string; level?: string; score_breakdown?: Record<string, unknown>; ai_summary?: string;
  is_reapplicant?: boolean; application_logs?: ApplicationLog[]; interview_prep?: InterviewPrep;
  prep_status?: string; question_prep_status?: string; interview_link?: string; cv_extracted_info?: Record<string, unknown>;
  interview_config?: Record<string, unknown>;
};
export type ApplicationLog = { id?: number|string; app_id?: string; event_type: string; message: string; details?: Record<string, unknown>; created_at?: string };
export type PrepQuestion = { n: string; text: string; type?: string; label?: string; audio_url?: string; is_ai_generated?: boolean; allow_follow_up?: boolean };
export type InterviewPrep = { prep_id: string; position_id?: string; created_at?: string; questions: PrepQuestion[]; follow_up_limit?: number };
export type Interview = {
  id: string; candidate_id?: string; candidate_name?: string; candidate_email?: string; position_id: string; level?: string;
  application_source?: string;
  status: string; submitted_at?: string; avg_score?: number | null; answer_count?: number; tab_switches?: number;
  hr_score?: number | null; hr_notes?: string; expert_score?: number | null; expert_notes?: string;
  answers?: InterviewAnswer[]; hod_questions?: string | string[]; overall_strengths?: string; overall_weaknesses?: string;
};
export type InterviewAnswer = { question_number: string; question_type?: string; question_text?: string; transcript?: string; ai_level?: string; ai_feedback?: string; duration_sec?: number; time_spent?: number; score?: number | null; notes?: string; attempt_number?: number | null };
export type ApiErrorShape = { detail?: string | { message?: string }; msg?: string; message?: string };
