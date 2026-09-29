<script lang="ts">
	import { fly, scale, slide } from 'svelte/transition';
	import Confetti from '$lib/Confetti.svelte';
	import { motion } from '$lib/motion';
	import { parseCodeSegments } from '$lib/textUtils';
	import type { QuizQuestion } from '$lib/types';

	let {
		questions,
		title,
		onClose,
		onRetake
	}: {
		questions: QuizQuestion[];
		title: string;
		onClose: () => void;
		onRetake?: () => void;
	} = $props();

	const CELEBRATE_AT_PERCENT = 80;
	const RING_RADIUS = 42;
	const RING_LENGTH = 2 * Math.PI * RING_RADIUS;

	let index = $state(0);
	let answers: (number | undefined)[] = $state([]);
	let showResults = $state(false);
	let reviewOpen = $state(false);

	let question = $derived(questions[index]);
	let selected = $derived(answers[index]);
	let answeredCount = $derived(answers.filter((a) => a !== undefined).length);
	let correctCount = $derived(questions.filter((q, i) => answers[i] === q.answer_index).length);
	let percent = $derived(questions.length ? Math.round((correctCount / questions.length) * 100) : 0);
	// Dots can jump back to answered questions, or to the first unanswered one.
	let furthest = $derived.by(() => {
		const firstOpen = questions.findIndex((_, i) => answers[i] === undefined);
		return firstOpen === -1 ? questions.length - 1 : firstOpen;
	});
	let mistakes = $derived(
		questions
			.map((q, i) => ({ q, i, answer: answers[i] }))
			.filter((m) => m.answer !== undefined && m.answer !== m.q.answer_index)
	);
	let verdict = $derived(
		percent >= CELEBRATE_AT_PERCENT
			? 'Excellent work!'
			: percent >= 50
				? 'Good effort — review the ones you missed.'
				: 'Keep going — revisit the topics and try again.'
	);

	function choose(option: number) {
		if (answers[index] !== undefined) return;
		answers[index] = option;
	}

	function next() {
		if (index + 1 < questions.length) {
			index += 1;
		} else {
			showResults = true;
		}
	}

	function goTo(i: number) {
		showResults = false;
		index = i;
	}
</script>

{#snippet quizText(text: string)}
	{#each parseCodeSegments(text) as segment}
		{#if segment.type === 'code'}
			<pre class="quiz-code"><code>{segment.content}</code></pre>
		{:else if segment.content.trim()}
			<span>{segment.content}</span>
		{/if}
	{/each}
{/snippet}

<div class="ai-panel quiz-runner" transition:slide={motion({ duration: 200 })}>
	<button class="ai-panel-close" aria-label="Close quiz" onclick={onClose}>×</button>

	<div class="quiz-header">
		<strong>{title}</strong>
		<span class="quiz-progress">
			{#if !showResults}Question {index + 1} of {questions.length} ·{/if}
			Score {correctCount}/{answeredCount}
		</span>
	</div>

	<div class="quiz-dots">
		{#each questions as q, i}
			<button
				class="quiz-dot"
				class:current={!showResults && i === index}
				class:right={answers[i] !== undefined && answers[i] === q.answer_index}
				class:wrong={answers[i] !== undefined && answers[i] !== q.answer_index}
				disabled={i > furthest}
				aria-label="Go to question {i + 1}"
				onclick={() => goTo(i)}
			></button>
		{/each}
	</div>

	{#if showResults}
		<div class="quiz-results" in:scale={motion({ start: 0.94, duration: 250 })}>
			<svg class="score-ring" viewBox="0 0 100 100" role="img" aria-label="{percent}% correct">
				<circle class="score-ring-track" cx="50" cy="50" r={RING_RADIUS} />
				<circle
					class="score-ring-fill"
					class:high={percent >= CELEBRATE_AT_PERCENT}
					cx="50"
					cy="50"
					r={RING_RADIUS}
					stroke-dasharray={RING_LENGTH}
					stroke-dashoffset={RING_LENGTH * (1 - percent / 100)}
				/>
				<text x="50" y="50" class="score-ring-text">{percent}%</text>
			</svg>
			<p class="quiz-verdict">{verdict}</p>
			<p class="quiz-summary">{correctCount} of {questions.length} correct</p>

			{#if mistakes.length}
				<button class="review-toggle" onclick={() => (reviewOpen = !reviewOpen)}>
					{reviewOpen ? 'Hide mistakes' : `Review mistakes (${mistakes.length})`}
				</button>
				{#if reviewOpen}
					<ol class="mistake-list" transition:slide={motion({ duration: 200 })}>
						{#each mistakes as m}
							<li>
								<div class="quiz-question">{@render quizText(m.q.question)}</div>
								<p class="mistake-answer wrong-answer">
									Your answer: {@render quizText(m.q.options[m.answer!])}
								</p>
								<p class="mistake-answer right-answer">
									Correct: {@render quizText(m.q.options[m.q.answer_index])}
								</p>
								<div class="quiz-explanation">{@render quizText(m.q.explanation)}</div>
							</li>
						{/each}
					</ol>
				{/if}
			{/if}

			<div class="quiz-result-actions">
				{#if onRetake}
					<button class="quiz-next-btn" onclick={onRetake}>Retake quiz</button>
				{/if}
				<button class="ai-action-btn" onclick={onClose}>Close</button>
			</div>
		</div>
		{#if percent >= CELEBRATE_AT_PERCENT}
			<Confetti />
		{/if}
	{:else}
		{#key index}
			<div class="quiz-step" in:fly={motion({ x: 24, duration: 220 })}>
				{#if question.difficulty}
					<span class="difficulty-badge difficulty-{question.difficulty}">{question.difficulty}</span>
				{/if}
				<div class="quiz-question">{@render quizText(question.question)}</div>
				<div class="quiz-options">
					{#each question.options as option, idx}
						<button
							class="quiz-option"
							class:correct={selected !== undefined && idx === question.answer_index}
							class:incorrect={selected === idx && idx !== question.answer_index}
							disabled={selected !== undefined}
							onclick={() => choose(idx)}
						>
							{@render quizText(option)}
						</button>
					{/each}
				</div>

				{#if selected !== undefined}
					<div class="quiz-feedback-block" transition:slide={motion({ duration: 180 })}>
						<p class="quiz-feedback" class:right={selected === question.answer_index}>
							{selected === question.answer_index ? 'Correct' : 'Not quite'}
						</p>
						<div class="quiz-explanation">{@render quizText(question.explanation)}</div>
						<button class="quiz-next-btn" onclick={next}>
							{index + 1 < questions.length ? 'Next question →' : 'See results'}
						</button>
					</div>
				{/if}
			</div>
		{/key}
	{/if}
</div>

<style>
	.quiz-dots {
		display: flex;
		flex-wrap: wrap;
		gap: 0.35rem;
		margin: 0.5rem 0 0.25rem;
	}

	.quiz-dot {
		width: 0.7rem;
		height: 0.7rem;
		padding: 0;
		border-radius: 50%;
		border: 1px solid var(--border-color);
		background: var(--surface-hover);
		cursor: pointer;
		transition:
			transform 0.15s,
			background 0.2s;
	}

	.quiz-dot:disabled {
		cursor: default;
		opacity: 0.6;
	}

	.quiz-dot:hover:not(:disabled) {
		transform: scale(1.25);
		box-shadow: none;
	}

	.quiz-dot.current {
		border-color: #ff3e00;
		box-shadow: 0 0 0 2px color-mix(in srgb, #ff3e00 30%, transparent);
	}

	.quiz-dot.right {
		background: #2e9e5b;
		border-color: #2e9e5b;
	}

	.quiz-dot.wrong {
		background: #c53000;
		border-color: #c53000;
	}

	.quiz-option.correct {
		animation: quiz-pop 0.35s ease-out;
	}

	.quiz-option.incorrect {
		animation: quiz-shake 0.4s ease-in-out;
	}

	@keyframes quiz-pop {
		50% {
			transform: scale(1.03);
		}
	}

	@keyframes quiz-shake {
		20%,
		60% {
			transform: translateX(-5px);
		}
		40%,
		80% {
			transform: translateX(5px);
		}
	}

	.quiz-feedback {
		margin: 0.6rem 0 0;
		font-weight: 700;
		color: #c53000;
	}

	.quiz-feedback.right {
		color: #2e9e5b;
	}

	.quiz-results {
		text-align: center;
		padding: 0.5rem 0;
	}

	.score-ring {
		width: 7.5rem;
		height: 7.5rem;
	}

	.score-ring-track {
		fill: none;
		stroke: var(--surface-hover);
		stroke-width: 9;
	}

	.score-ring-fill {
		fill: none;
		stroke: #e0a800;
		stroke-width: 9;
		stroke-linecap: round;
		transform: rotate(-90deg);
		transform-origin: 50% 50%;
		animation: ring-fill 0.9s ease-out;
	}

	.score-ring-fill.high {
		stroke: #2e9e5b;
	}

	@keyframes ring-fill {
		from {
			stroke-dashoffset: 264;
		}
	}

	.score-ring-text {
		fill: var(--text-primary);
		font-size: 1.35rem;
		font-weight: 700;
		text-anchor: middle;
		dominant-baseline: central;
	}

	.quiz-verdict {
		margin: 0.5rem 0 0.15rem;
		font-weight: 700;
		font-size: 1.05rem;
		color: var(--text-primary);
	}

	.quiz-summary {
		margin: 0 0 0.75rem;
		color: var(--text-muted);
		font-size: 0.9rem;
	}

	.review-toggle {
		font-family: inherit;
		font-size: 0.85rem;
		font-weight: 600;
		padding: 0;
		border: none;
		background: none;
		color: #ff3e00;
		cursor: pointer;
	}

	.review-toggle:hover {
		transform: none;
		box-shadow: none;
		text-decoration: underline;
	}

	.mistake-list {
		text-align: left;
		margin: 0.75rem 0 0;
		padding-left: 1.25rem;
		display: flex;
		flex-direction: column;
		gap: 0.9rem;
	}

	.mistake-answer {
		margin: 0.3rem 0 0;
		font-size: 0.88rem;
	}

	.wrong-answer {
		color: #c53000;
	}

	.right-answer {
		color: #2e9e5b;
	}

	.quiz-result-actions {
		display: flex;
		justify-content: center;
		flex-wrap: wrap;
		gap: 0.5rem;
		margin-top: 1rem;
	}

	.quiz-result-actions .quiz-next-btn {
		margin-top: 0;
	}

	@media (prefers-reduced-motion: reduce) {
		.quiz-option.correct,
		.quiz-option.incorrect,
		.score-ring-fill {
			animation: none;
		}
	}
</style>
