<script lang="ts">
	import { page } from '$app/state';
	import { SvelteSet, SvelteMap } from 'svelte/reactivity';
	import { slide } from 'svelte/transition';
	import { auth } from '$lib/auth.svelte';
	import { languageLabel } from '$lib/languages';
	import { parseCodeSegments } from '$lib/textUtils';
	import { createQuizPrefetcher } from '$lib/quizPrefetch';
	import { fly } from 'svelte/transition';
	import QuizRunner from '$lib/QuizRunner.svelte';
	import Celebration from '$lib/Celebration.svelte';
	import { motion } from '$lib/motion';
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
	let copiedHeading: string | null = $state(null);

	let overallQuiz: QuizQuestion[] | null = $state(null);
	let overallQuizLoading = $state(false);
	let overallQuizError: string | null = $state(null);

	// Bumped to play the confetti when every topic is marked done.
	let celebrateAllDone = $state(0);

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
		overallQuiz = null;
		overallQuizError = null;
		doneTopics.clear();
		searchQuery = '';
		quizPrefetch.clear();
		shareToken = null;
		shareOpen = false;
		shareError = null;

		(async () => {
			try {
				const response = await auth.fetch(`/api/history/${id}`);
				const data = await response.json();
				if (!response.ok) throw new Error(data.detail ?? 'Failed to load this analysis');
				result = data as AnalyzeResponse;
				for (const heading of result.done_topics ?? []) doneTopics.add(heading);
				shareToken = result.share_token ?? null;
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
		if (
			doneTopics.has(heading) &&
			result &&
			allTopics(result.roadmap).every((t) => doneTopics.has(t.heading))
		) {
			celebrateAllDone += 1;
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

	// Generates each opened topic's quiz in the background so "Quiz me" is
	// usually instant.
	const quizPrefetch = createQuizPrefetcher();

	function toggleTopic(heading: string) {
		if (expandedTopics.has(heading)) {
			expandedTopics.delete(heading);
			quizPrefetch.cancel(heading);
		} else {
			expandedTopics.add(heading);
			const topic = result ? allTopics(result.roadmap).find((t) => t.heading === heading) : undefined;
			if (topic && !quizzes.has(heading)) quizPrefetch.schedule(topic);
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
	}

	function retakeQuiz(topic: Topic) {
		closeQuiz(topic.heading);
		runQuiz(topic);
	}

	async function runQuiz(topic: Topic) {
		if (quizLoading.has(topic.heading) || quizzes.has(topic.heading)) return;
		quizLoading.add(topic.heading);
		try {
			quizzes.set(topic.heading, await quizPrefetch.take(topic));
		} catch (err) {
			// Leave the quiz section empty; the Quiz me button stays available to retry.
		} finally {
			quizLoading.delete(topic.heading);
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
		} catch (err) {
			overallQuizError = err instanceof Error ? err.message : 'Something went wrong';
		} finally {
			overallQuizLoading = false;
		}
	}

	function closeOverallQuiz() {
		overallQuiz = null;
		overallQuizError = null;
	}

	function retakeOverallQuiz() {
		overallQuiz = null;
		runOverallQuiz();
	}

	function quizToMarkdown(questions: QuizQuestion[], heading: string): string {
		const lines = [`#### ${heading}`, ''];
		questions.forEach((q, i) => {
			lines.push(`${i + 1}. ${q.question}${q.difficulty ? ` _(${q.difficulty})_` : ''}`);
			q.options.forEach((opt, idx) => {
				const marker = idx === q.answer_index ? '- **(correct answer)**' : '-';
				lines.push(`   ${marker} ${opt}`);
			});
			lines.push(`   > ${q.explanation}`, '');
		});
		return lines.join('\n');
	}

	function topicToMarkdown(topic: Topic, depth: number): string {
		const lines: string[] = [];
		const hashes = '#'.repeat(Math.min(depth + 2, 6));
		lines.push(`${hashes} ${topic.heading}${doneTopics.has(topic.heading) ? ' (done)' : ''}`, '');
		lines.push(topic.content, '');
		if (topic.example) {
			lines.push('**Example:**', '```', topic.example, '```', '');
		}
		const explanation = aiExplanations.get(topic.heading);
		if (explanation?.length) {
			lines.push('**AI Explanation:**', '');
			for (const point of explanation) {
				lines.push(`- **${point.title}** — ${point.detail}`);
			}
			lines.push('');
		}
		const quiz = quizzes.get(topic.heading);
		if (quiz?.length) {
			lines.push(quizToMarkdown(quiz, 'Quiz'), '');
		}
		if (topic.resources?.length) {
			lines.push('**Related Videos:**', '');
			for (const r of topic.resources) {
				lines.push(`- [${r.title}](${r.url ?? '#'})`);
			}
			lines.push('');
		}
		if (topic.related?.length) {
			lines.push(`**Related topics:** ${topic.related.join(', ')}`, '');
		}
		for (const child of topic.children ?? []) {
			lines.push(topicToMarkdown(child, depth + 1));
		}
		return lines.join('\n');
	}

	function buildMarkdown(): string {
		if (!result) return '';
		const lines: string[] = [];
		lines.push(`# ${result.source ?? 'Video Analysis'}`, '');
		if (result.detected_language) {
			lines.push(`_Detected language: ${languageLabel(result.detected_language)}_`, '');
		}
		lines.push('## Intro', '', result.intro, '');
		lines.push('## Key Points', '');
		for (const point of result.key_points) lines.push(`- ${point}`);
		lines.push('');
		lines.push('## Roadmap', '');
		for (const topic of result.roadmap) lines.push(topicToMarkdown(topic, 0));
		if (overallQuiz?.length) {
			lines.push('## Final Quiz', '');
			lines.push(quizToMarkdown(overallQuiz, 'Full Video Quiz'));
		}
		return lines.join('\n');
	}

	// --- Public share link ---
	let shareToken: string | null = $state(null);
	let shareOpen = $state(false);
	let shareBusy = $state(false);
	let shareError: string | null = $state(null);
	let shareCopied = $state(false);

	let shareUrl = $derived(shareToken ? `${window.location.origin}/shared/${shareToken}` : '');

	async function copyShareUrl() {
		try {
			await navigator.clipboard.writeText(shareUrl);
			shareCopied = true;
			setTimeout(() => (shareCopied = false), 1500);
		} catch {
			// clipboard API unavailable/denied - the link is still visible to copy by hand
		}
	}

	async function openShare() {
		shareOpen = !shareOpen;
		if (!shareOpen || shareToken || !result?.id) return;
		shareBusy = true;
		shareError = null;
		try {
			const response = await auth.fetch(`/api/history/${result.id}/share`, { method: 'POST' });
			const data = await response.json();
			if (!response.ok) throw new Error(data.detail ?? 'Could not create a share link');
			shareToken = data.share_token;
			await copyShareUrl();
		} catch (err) {
			shareError = err instanceof Error ? err.message : 'Something went wrong';
		} finally {
			shareBusy = false;
		}
	}

	async function stopSharing() {
		if (!result?.id) return;
		shareBusy = true;
		shareError = null;
		try {
			const response = await auth.fetch(`/api/history/${result.id}/share`, { method: 'DELETE' });
			if (!response.ok) throw new Error((await response.json()).detail ?? 'Could not stop sharing');
			shareToken = null;
			shareOpen = false;
		} catch (err) {
			shareError = err instanceof Error ? err.message : 'Something went wrong';
		} finally {
			shareBusy = false;
		}
	}

	function downloadMarkdown() {
		if (!result) return;
		const markdown = buildMarkdown();
		const blob = new Blob([markdown], { type: 'text/markdown' });
		const url = URL.createObjectURL(blob);
		const a = document.createElement('a');
		const safeName = (result.source ?? 'analysis').replace(/[^a-z0-9]+/gi, '-').toLowerCase();
		a.href = url;
		a.download = `${safeName || 'analysis'}.md`;
		document.body.appendChild(a);
		a.click();
		a.remove();
		URL.revokeObjectURL(url);
	}
</script>

<a class="back-link" href="/">← Back to upload</a>

{#if loading}
	<p class="status"><span class="spinner"></span> Loading analysis…</p>
{:else if loadError}
	<p class="error">{loadError}</p>
{:else if result}
	<Celebration trigger={celebrateAllDone} message="You've completed every topic!" />
	<section class="results card" in:fly|global={motion({ y: 16, duration: 350 })}>
		<div class="results-header">
			{#if result.detected_language}
				<span class="language-badge">Detected language: {languageLabel(result.detected_language)}</span>
			{/if}
			<button class="ai-action-btn export-btn" onclick={downloadMarkdown}>Download as Markdown</button>
			<button class="ai-action-btn" onclick={openShare}>{shareToken ? 'Shared' : 'Share'}</button>
		</div>

		{#if shareOpen}
			<div class="share-panel" transition:slide={{ duration: 150 }}>
				{#if shareBusy && !shareToken}
					<p class="ai-loading">Creating link…</p>
				{:else if shareToken}
					<p class="share-hint">Anyone with this link can view this roadmap (read-only, no login needed).</p>
					<div class="share-row">
						<input class="url-input share-input" readonly value={shareUrl} onfocus={(e) => e.currentTarget.select()} />
						<button class="ai-action-btn" onclick={copyShareUrl}>{shareCopied ? 'Copied!' : 'Copy'}</button>
						<button class="ai-action-btn" disabled={shareBusy} onclick={stopSharing}>Stop sharing</button>
					</div>
				{/if}
				{#if shareError}
					<p class="ai-error">{shareError}</p>
				{/if}
			</div>
		{/if}

		<div class="summary-row" class:quiz-active={overallQuiz !== null}>
			<p class="intro">{result.intro}</p>

			<div class="overall-quiz-section final-quiz-card">
				<h2>Final Quiz</h2>
				<p class="roadmap-hint">Test yourself on the whole video — 10–15 questions.</p>

				{#if !overallQuiz}
					<button class="ai-action-btn overall-quiz-btn" disabled={overallQuizLoading} onclick={runOverallQuiz}>
						{overallQuizLoading ? 'Generating quiz…' : 'Start Final Quiz'}
					</button>
					{#if overallQuizError}
						<p class="ai-error">{overallQuizError}</p>
					{/if}
				{:else}
					{#key overallQuiz}
						<QuizRunner
							questions={overallQuiz}
							title="Full Video Quiz"
							onClose={closeOverallQuiz}
							onRetake={retakeOverallQuiz}
						/>
					{/key}
				{/if}
			</div>
		</div>

		<h2>Key Points</h2>
		<ul class="key-points">
			{#each result.key_points as point, i}
				<li in:fly|global={motion({ y: 8, delay: 120 + i * 70, duration: 280 })}>{point}</li>
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
						{#key quizzes.get(topic.heading)}
							<QuizRunner
								questions={quizzes.get(topic.heading)!}
								title="Quiz"
								onClose={() => closeQuiz(topic.heading)}
								onRetake={() => retakeQuiz(topic)}
							/>
						{/key}
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
				<div class="roadmap-node" in:fly|global={motion({ y: 12, delay: Math.min(i, 8) * 60, duration: 300 })}>
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

	</section>
{/if}
