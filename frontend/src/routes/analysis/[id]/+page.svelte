<script lang="ts">
	import { page } from '$app/state';
	import { SvelteSet, SvelteMap } from 'svelte/reactivity';
	import { slide } from 'svelte/transition';
	import { auth } from '$lib/auth.svelte';
	import { languageLabel } from '$lib/languages';
	import { parseCodeSegments } from '$lib/textUtils';
	import type { AnalyzeResponse, Topic, Resource, QuizQuestion, ExplainPoint } from '$lib/types';

	let analysisId = $derived(page.params.id);

	let loading = $state(true);
	let loadError: string | null = $state(null);
	let result: AnalyzeResponse | null = $state(null);

	let expandedTopics = new SvelteSet<string>();
	let aiExplanations = new SvelteMap<string, ExplainPoint[]>();
	let explainLoading = new SvelteSet<string>();
	let explainErrors = new SvelteMap<string, string>();
	let expandedExplainPoints = new SvelteSet<string>();
	let quizzes = new SvelteMap<string, QuizQuestion[]>();
	let quizLoading = new SvelteSet<string>();
	let quizIndex = new SvelteMap<string, number>();
	let quizSelected = new SvelteMap<string, number>();
	let copiedHeading: string | null = $state(null);

	let overallQuiz: QuizQuestion[] | null = $state(null);
	let overallQuizLoading = $state(false);
	let overallQuizError: string | null = $state(null);
	let overallQuizIndex = $state(0);
	let overallQuizSelected = new SvelteMap<number, number>();

	let doneTopics = new SvelteSet<string>();
	let searchQuery = $state('');

	$effect(() => {
		const id = analysisId;

		// Reset everything - covers both first load and navigating from one
		// analysis id to another without a full remount.
		loading = true;
		loadError = null;
		result = null;
		expandedTopics.clear();
		aiExplanations.clear();
		explainLoading.clear();
		explainErrors.clear();
		expandedExplainPoints.clear();
		quizzes.clear();
		quizLoading.clear();
		quizIndex.clear();
		quizSelected.clear();
		overallQuiz = null;
		overallQuizError = null;
		overallQuizIndex = 0;
		overallQuizSelected.clear();
		doneTopics.clear();
		searchQuery = '';

		(async () => {
			try {
				const response = await auth.fetch(`/api/history/${id}`);
				const data = await response.json();
				if (!response.ok) throw new Error(data.detail ?? 'Failed to load this analysis');
				result = data as AnalyzeResponse;
				for (const heading of result.done_topics ?? []) doneTopics.add(heading);
			} catch (err) {
				loadError = err instanceof Error ? err.message : 'Something went wrong';
			} finally {
				loading = false;
			}
		})();
	});

	async function toggleTopicDone(heading: string, event: Event) {
		event.stopPropagation();
		if (!result?.id) return;
		if (doneTopics.has(heading)) {
			doneTopics.delete(heading);
		} else {
			doneTopics.add(heading);
		}
		try {
			await auth.fetch(`/api/history/${result.id}/done-topics`, {
				method: 'PUT',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ done_topics: [...doneTopics] })
			});
		} catch {
			// best-effort - the checkbox already reflects the change locally
		}
	}

	function allTopics(roadmap: Topic[]): Topic[] {
		const all: Topic[] = [];
		for (const topic of roadmap) {
			all.push(topic);
			for (const child of topic.children ?? []) all.push(child);
		}
		return all;
	}

	let progress = $derived.by(() => {
		if (!result) return { done: 0, total: 0 };
		const topics = allTopics(result.roadmap);
		const done = topics.filter((t) => doneTopics.has(t.heading)).length;
		return { done, total: topics.length };
	});

	function topicMatches(topic: Topic, query: string) {
		const q = query.toLowerCase();
		return topic.heading.toLowerCase().includes(q) || topic.content.toLowerCase().includes(q);
	}

	let filteredRoadmap = $derived.by(() => {
		if (!result) return [];
		const query = searchQuery.trim();
		if (!query) return result.roadmap;
		const out: Topic[] = [];
		for (const topic of result.roadmap) {
			const selfMatches = topicMatches(topic, query);
			const matchingChildren = (topic.children ?? []).filter((c) => topicMatches(c, query));
			if (selfMatches || matchingChildren.length) {
				out.push(selfMatches ? topic : { ...topic, children: matchingChildren });
			}
		}
		return out;
	});

	async function copyExample(heading: string, text: string) {
		try {
			await navigator.clipboard.writeText(text);
			copiedHeading = heading;
			setTimeout(() => {
				if (copiedHeading === heading) copiedHeading = null;
			}, 1500);
		} catch {
			// clipboard API unavailable/denied - silently do nothing
		}
	}

	function topicSlug(heading: string) {
		return 'topic-' + heading.toLowerCase().replace(/[^a-z0-9]+/g, '-');
	}

	function toggleTopic(heading: string) {
		if (expandedTopics.has(heading)) {
			expandedTopics.delete(heading);
		} else {
			expandedTopics.add(heading);
		}
	}

	function jumpToRelated(heading: string) {
		expandedTopics.add(heading);
		document.getElementById(topicSlug(heading))?.scrollIntoView({ behavior: 'smooth', block: 'center' });
	}

	function resourceHref(resource: Resource) {
		return resource.url ?? `https://www.google.com/search?q=${encodeURIComponent(resource.title)}`;
	}

	async function runExplain(topic: Topic) {
		if (explainLoading.has(topic.heading) || aiExplanations.has(topic.heading)) return;
		explainLoading.add(topic.heading);
		explainErrors.delete(topic.heading);
		try {
			const response = await auth.fetch('/api/topic/explain', {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({
					heading: topic.heading,
					content: topic.content,
					example: topic.example ?? null
				})
			});
			const data = await response.json();
			if (!response.ok) throw new Error(data.detail ?? 'Failed to get an explanation');
			aiExplanations.set(topic.heading, data.points as ExplainPoint[]);
		} catch (err) {
			explainErrors.set(
				topic.heading,
				err instanceof Error ? `Couldn't load an explanation: ${err.message}` : 'Something went wrong'
			);
		} finally {
			explainLoading.delete(topic.heading);
		}
	}

	function explainPointKey(heading: string, pointIndex: number) {
		return `${heading}#${pointIndex}`;
	}

	function toggleExplainPoint(heading: string, pointIndex: number) {
		const key = explainPointKey(heading, pointIndex);
		if (expandedExplainPoints.has(key)) {
			expandedExplainPoints.delete(key);
		} else {
			expandedExplainPoints.add(key);
		}
	}

	function closeExplain(heading: string) {
		aiExplanations.delete(heading);
		explainErrors.delete(heading);
		for (const key of [...expandedExplainPoints]) {
			if (key.startsWith(`${heading}#`)) expandedExplainPoints.delete(key);
		}
	}

	function closeQuiz(heading: string) {
		quizzes.delete(heading);
		quizIndex.delete(heading);
		for (const key of [...quizSelected.keys()]) {
			if (key.startsWith(`${heading}#`)) quizSelected.delete(key);
		}
	}

	async function runQuiz(topic: Topic) {
		if (quizLoading.has(topic.heading) || quizzes.has(topic.heading)) return;
		quizLoading.add(topic.heading);
		try {
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
			quizzes.set(topic.heading, data.questions as QuizQuestion[]);
			quizIndex.set(topic.heading, 0);
		} catch (err) {
			// Leave the quiz section empty; the Quiz me button stays available to retry.
		} finally {
			quizLoading.delete(topic.heading);
		}
	}

	function quizAnswerKey(heading: string, questionIndex: number) {
		return `${heading}#${questionIndex}`;
	}

	function selectQuizOption(heading: string, questionIndex: number, optionIndex: number) {
		const key = quizAnswerKey(heading, questionIndex);
		if (quizSelected.has(key)) return;
		quizSelected.set(key, optionIndex);
	}

	function nextQuizQuestion(heading: string) {
		const total = quizzes.get(heading)?.length ?? 0;
		const current = quizIndex.get(heading) ?? 0;
		if (current + 1 < total) {
			quizIndex.set(heading, current + 1);
		}
	}

	async function runOverallQuiz() {
		if (!result || overallQuizLoading || overallQuiz) return;
		overallQuizLoading = true;
		overallQuizError = null;
		try {
			const response = await auth.fetch('/api/quiz/overall', {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ roadmap: result.roadmap })
			});
			const data = await response.json();
			if (!response.ok) throw new Error(data.detail ?? 'Failed to generate the quiz');
			overallQuiz = data.questions as QuizQuestion[];
			overallQuizIndex = 0;
			overallQuizSelected.clear();
		} catch (err) {
			overallQuizError = err instanceof Error ? err.message : 'Something went wrong';
		} finally {
			overallQuizLoading = false;
		}
	}

	function selectOverallOption(questionIndex: number, optionIndex: number) {
		if (overallQuizSelected.has(questionIndex)) return;
		overallQuizSelected.set(questionIndex, optionIndex);
	}

	function nextOverallQuestion() {
		const total = overallQuiz?.length ?? 0;
		if (overallQuizIndex + 1 < total) overallQuizIndex += 1;
	}

	function closeOverallQuiz() {
		overallQuiz = null;
		overallQuizError = null;
		overallQuizIndex = 0;
		overallQuizSelected.clear();
	}

	function retakeOverallQuiz() {
		overallQuiz = null;
		overallQuizIndex = 0;
		overallQuizSelected.clear();
		runOverallQuiz();
	}
</script>

<a class="back-link" href="/">← Back to upload</a>

{#if loading}
	<p class="status"><span class="spinner"></span> Loading analysis…</p>
{:else if loadError}
	<p class="error">{loadError}</p>
{:else if result}
	<section class="results card">
		{#if result.detected_language}
			<span class="language-badge">Detected language: {languageLabel(result.detected_language)}</span>
		{/if}

		<p class="intro">{result.intro}</p>

		<h2>Key Points</h2>
		<ul class="key-points">
			{#each result.key_points as point}
				<li>{point}</li>
			{/each}
		</ul>

		{#if progress.total > 0}
			<div class="progress-wrap">
				<div class="progress-label">
					<span>Study progress</span>
					<span>{progress.done} / {progress.total} topics done</span>
				</div>
				<div class="progress-bar">
					<div class="progress-fill" style:width="{(progress.done / progress.total) * 100}%"></div>
				</div>
			</div>
		{/if}

		<input type="search" class="topic-search" placeholder="Search roadmap topics…" bind:value={searchQuery} />

		{#snippet quizText(text: string)}
			{#each parseCodeSegments(text) as segment}
				{#if segment.type === 'code'}
					<pre class="quiz-code"><code>{segment.content}</code></pre>
				{:else if segment.content.trim()}
					<span>{segment.content}</span>
				{/if}
			{/each}
		{/snippet}

		{#snippet topicDetails(topic: Topic)}
			{#if expandedTopics.has(topic.heading)}
				<div class="node-details" transition:slide={{ duration: 200 }}>
					<button class="close-topic-btn" aria-label="Close topic" onclick={() => toggleTopic(topic.heading)}>
						×
					</button>

					<label class="done-checkbox">
						<input
							type="checkbox"
							checked={doneTopics.has(topic.heading)}
							onclick={(e) => toggleTopicDone(topic.heading, e)}
						/>
						Mark as done
					</label>

					<p class="explanation">{topic.content}</p>
					{#if topic.example}
						<div class="example">
							<p><strong>Example:</strong> {topic.example}</p>
							<button class="copy-btn" onclick={() => copyExample(topic.heading, topic.example ?? '')}>
								{copiedHeading === topic.heading ? 'Copied!' : 'Copy'}
							</button>
						</div>
					{/if}

					<div class="ai-actions">
						<span class="ai-actions-label">Learn with AI</span>
						<button class="ai-action-btn" onclick={() => runExplain(topic)}>Explain</button>
						<button class="ai-action-btn" onclick={() => runQuiz(topic)}>Quiz me</button>
					</div>

					{#if explainLoading.has(topic.heading)}
						<p class="ai-loading">Thinking…</p>
					{:else if explainErrors.has(topic.heading)}
						<p class="ai-error">{explainErrors.get(topic.heading)}</p>
					{:else if aiExplanations.has(topic.heading)}
						{@const points = aiExplanations.get(topic.heading)!}
						<div class="ai-panel">
							<button
								class="ai-panel-close"
								aria-label="Close AI explanation"
								onclick={() => closeExplain(topic.heading)}
							>
								×
							</button>
							<strong>AI Explanation</strong>
							<p class="ai-panel-hint">Click a point to expand it.</p>
							<ul class="explain-points">
								{#each points as point, idx}
									{@const key = explainPointKey(topic.heading, idx)}
									{@const isOpen = expandedExplainPoints.has(key)}
									<li>
										<button
											class="explain-point-toggle"
											class:open={isOpen}
											onclick={() => toggleExplainPoint(topic.heading, idx)}
										>
											<span class="explain-point-chevron">▸</span>
											{point.title}
										</button>
										{#if isOpen}
											<p class="explain-point-detail" transition:slide={{ duration: 150 }}>
												{point.detail}
											</p>
										{/if}
									</li>
								{/each}
							</ul>
						</div>
					{/if}

					{#if quizLoading.has(topic.heading)}
						<p class="ai-loading">Generating quiz questions…</p>
					{:else if quizzes.has(topic.heading)}
						{@const questions = quizzes.get(topic.heading)!}
						{@const qIndex = quizIndex.get(topic.heading) ?? 0}
						{@const question = questions[qIndex]}
						{@const selected = quizSelected.get(quizAnswerKey(topic.heading, qIndex))}
						<div class="ai-panel">
							<button class="ai-panel-close" aria-label="Close quiz" onclick={() => closeQuiz(topic.heading)}>
								×
							</button>
							<div class="quiz-header">
								<strong>Quiz</strong>
								<span class="quiz-progress">Question {qIndex + 1} of {questions.length}</span>
							</div>
							{#if question.difficulty}
								<span class="difficulty-badge difficulty-{question.difficulty}">
									{question.difficulty}
								</span>
							{/if}
							<div class="quiz-question">{@render quizText(question.question)}</div>
							<div class="quiz-options">
								{#each question.options as option, idx}
									<button
										class="quiz-option"
										class:correct={selected !== undefined && idx === question.answer_index}
										class:incorrect={selected === idx && idx !== question.answer_index}
										disabled={selected !== undefined}
										onclick={() => selectQuizOption(topic.heading, qIndex, idx)}
									>
										{@render quizText(option)}
									</button>
								{/each}
							</div>
							{#if selected !== undefined}
								<div class="quiz-explanation">{@render quizText(question.explanation)}</div>
								{#if qIndex + 1 < questions.length}
									<button class="quiz-next-btn" onclick={() => nextQuizQuestion(topic.heading)}>
										Next question →
									</button>
								{:else}
									<p class="quiz-done">Quiz complete for this topic.</p>
								{/if}
							{/if}
						</div>
					{/if}

					{#if topic.resources && topic.resources.length}
						<div class="resources">
							<strong>Related Videos</strong>
							{#each topic.resources as resource}
								<a class="resource-link" href={resourceHref(resource)} target="_blank" rel="noopener noreferrer">
									{resource.title}
								</a>
							{/each}
						</div>
					{/if}

					{#if topic.related && topic.related.length}
						<div class="related">
							<span class="related-label">Related:</span>
							{#each topic.related as rel}
								<button class="related-link" onclick={() => jumpToRelated(rel)}>{rel}</button>
							{/each}
						</div>
					{/if}
				</div>
			{/if}
		{/snippet}

		<h2>Roadmap</h2>
		<p class="roadmap-hint">Click a topic to expand it.</p>
		{#if searchQuery.trim() && filteredRoadmap.length === 0}
			<p class="roadmap-hint">No topics match "{searchQuery}".</p>
		{/if}
		<div class="roadmap">
			{#each filteredRoadmap as topic, i}
				<div class="roadmap-node">
					<div class="node-marker" class:marker-active={expandedTopics.has(topic.heading)}>
						{i + 1}
					</div>
					<div class="node-body">
						<button
							class="node-box main"
							class:expanded={expandedTopics.has(topic.heading)}
							id={topicSlug(topic.heading)}
							onclick={() => toggleTopic(topic.heading)}
						>
							{topic.heading}
						</button>
						{@render topicDetails(topic)}
						{#if topic.children && topic.children.length}
							<div class="branches">
								{#each topic.children as child}
									<div class="branch">
										<button
											class="node-box sub"
											class:expanded={expandedTopics.has(child.heading)}
											id={topicSlug(child.heading)}
											onclick={() => toggleTopic(child.heading)}
										>
											{child.heading}
										</button>
										{@render topicDetails(child)}
									</div>
								{/each}
							</div>
						{/if}
					</div>
				</div>
			{/each}
		</div>

		<div class="overall-quiz-section">
			<h2>Final Quiz</h2>
			<p class="roadmap-hint">Finished going through the roadmap? Test yourself across all of it.</p>

			{#if !overallQuiz}
				<button class="ai-action-btn overall-quiz-btn" disabled={overallQuizLoading} onclick={runOverallQuiz}>
					{overallQuizLoading ? 'Generating quiz…' : 'Take Full Quiz (10-15 questions)'}
				</button>
				{#if overallQuizError}
					<p class="ai-error">{overallQuizError}</p>
				{/if}
			{:else}
				{@const question = overallQuiz[overallQuizIndex]}
				{@const selected = overallQuizSelected.get(overallQuizIndex)}
				<div class="ai-panel overall-quiz-panel" transition:slide={{ duration: 200 }}>
					<button class="ai-panel-close" aria-label="Close quiz" onclick={closeOverallQuiz}>×</button>
					<div class="quiz-header">
						<strong>Full Video Quiz</strong>
						<span class="quiz-progress">
							Question {overallQuizIndex + 1} of {overallQuiz.length}
						</span>
					</div>
					{#if question.difficulty}
						<span class="difficulty-badge difficulty-{question.difficulty}">
							{question.difficulty}
						</span>
					{/if}
					<div class="quiz-question">{@render quizText(question.question)}</div>
					<div class="quiz-options">
						{#each question.options as option, idx}
							<button
								class="quiz-option"
								class:correct={selected !== undefined && idx === question.answer_index}
								class:incorrect={selected === idx && idx !== question.answer_index}
								disabled={selected !== undefined}
								onclick={() => selectOverallOption(overallQuizIndex, idx)}
							>
								{@render quizText(option)}
							</button>
						{/each}
					</div>
					{#if selected !== undefined}
						<div class="quiz-explanation">{@render quizText(question.explanation)}</div>
						{#if overallQuizIndex + 1 < overallQuiz.length}
							<button class="quiz-next-btn" onclick={nextOverallQuestion}>Next question →</button>
						{:else}
							{@const correctCount = [...overallQuizSelected.entries()].filter(
								([qIdx, sel]) => overallQuiz![qIdx].answer_index === sel
							).length}
							<p class="quiz-done">
								Quiz complete — you scored {correctCount} / {overallQuiz.length}.
							</p>
							<button class="quiz-next-btn" onclick={retakeOverallQuiz}>Retake quiz</button>
						{/if}
					{/if}
				</div>
			{/if}
		</div>
	</section>
{/if}
