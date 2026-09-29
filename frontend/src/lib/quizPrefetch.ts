import { auth } from './auth.svelte';
import type { QuizQuestion, Topic } from './types';

// Wait this long after a topic is opened before generating its quiz, so
// quickly clicking through topics doesn't fire a Gemini request for each.
const PREFETCH_DELAY_MS = 1500;

async function fetchQuiz(topic: Topic): Promise<QuizQuestion[]> {
	const response = await auth.fetch('/api/topic/quiz', {
		method: 'POST',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify({
			heading: topic.heading,
			content: topic.content,
			example: topic.example ?? null
		})
	});
	const data = await response.json();
	if (!response.ok) throw new Error(data.detail ?? 'Failed to generate a quiz');
	return data.questions as QuizQuestion[];
}

/** Generates a topic's quiz in the background while it's open, so "Quiz me"
 * is usually instant. Each prepared quiz is handed out once; asking again
 * after that generates a fresh one. */
export function createQuizPrefetcher() {
	const pending = new Map<string, Promise<QuizQuestion[]>>();
	const timers = new Map<string, ReturnType<typeof setTimeout>>();

	function cancel(heading: string) {
		clearTimeout(timers.get(heading));
		timers.delete(heading);
	}

	return {
		/** Call when a topic is opened. */
		schedule(topic: Topic) {
			if (pending.has(topic.heading) || timers.has(topic.heading)) return;
			timers.set(
				topic.heading,
				setTimeout(() => {
					timers.delete(topic.heading);
					const quiz = fetchQuiz(topic);
					quiz.catch(() => pending.delete(topic.heading));
					pending.set(topic.heading, quiz);
				}, PREFETCH_DELAY_MS)
			);
		},

		/** Call when a topic is closed before its quiz started generating. */
		cancel,

		/** The prepared quiz if there is one (waiting for it if it's still
		 * generating), otherwise a freshly generated one. */
		take(topic: Topic): Promise<QuizQuestion[]> {
			cancel(topic.heading);
			const quiz = pending.get(topic.heading);
			pending.delete(topic.heading);
			return quiz ? quiz.catch(() => fetchQuiz(topic)) : fetchQuiz(topic);
		},

		clear() {
			for (const timer of timers.values()) clearTimeout(timer);
			timers.clear();
			pending.clear();
		}
	};
}
