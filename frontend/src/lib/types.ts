export type Resource = {
	type: 'article' | 'video';
	title: string;
	url?: string;
};

export type Topic = {
	heading: string;
	content: string;
	example?: string;
	related?: string[];
	resources?: Resource[];
	children?: Topic[];
};

export type AnalyzeResponse = {
	success: boolean;
	id?: number;
	intro: string;
	key_points: string[];
	roadmap: Topic[];
	source?: string;
	detected_language?: string | null;
	done_topics?: string[];
	share_token?: string | null;
};

export type QuizQuestion = {
	question: string;
	options: string[];
	answer_index: number;
	explanation: string;
	difficulty?: 'easy' | 'medium' | 'hard';
};

export type ExplainPoint = {
	title: string;
	detail: string;
};

export type HistoryEntry = {
	id: number;
	source: string;
	intro: string;
	created_at: string;
	done_count: number;
	total_count: number;
};

export type TextSegment = { type: 'text' | 'code'; content: string };

export type AnalyzeProgressEvent = { type: 'progress'; step: string; message: string };

export type SharedAnalysis = {
	source: string;
	intro: string;
	key_points: string[];
	roadmap: Topic[];
	detected_language?: string | null;
	created_at: string;
};
