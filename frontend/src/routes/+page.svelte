<script lang="ts">
	import { onMount } from 'svelte';
	import { SvelteSet, SvelteMap } from 'svelte/reactivity';
	import { slide } from 'svelte/transition';

	type UiState = 'IDLE' | 'FILE_SELECTED' | 'PROCESSING' | 'SUCCESS' | 'ERROR';

	type Resource = {
		type: 'article' | 'video';
		title: string;
		url?: string;
	};

	type Topic = {
		heading: string;
		content: string;
		example?: string;
		related?: string[];
		resources?: Resource[];
		children?: Topic[];
	};

	type AnalyzeResponse = {
		success: boolean;
		intro: string;
		key_points: string[];
		roadmap: Topic[];
		source?: string;
		detected_language?: string | null;
	};

	type QuizQuestion = {
		question: string;
		options: string[];
		answer_index: number;
		explanation: string;
		difficulty?: 'easy' | 'medium' | 'hard';
	};

	type ExplainPoint = {
		title: string;
		detail: string;
	};

	const LANGUAGE_NAMES: Record<string, string> = {
		en: 'English',
		es: 'Spanish',
		fr: 'French',
		de: 'German',
		hi: 'Hindi',
		ta: 'Tamil',
		te: 'Telugu',
		kn: 'Kannada',
		ml: 'Malayalam',
		zh: 'Chinese',
		ja: 'Japanese',
		ko: 'Korean',
		pt: 'Portuguese',
		ru: 'Russian',
		ar: 'Arabic',
		it: 'Italian'
	};

	function languageLabel(code: string) {
		return LANGUAGE_NAMES[code] ?? code.toUpperCase();
	}

	type TextSegment = { type: 'text' | 'code'; content: string };

	function parseCodeSegments(text: string): TextSegment[] {
		const segments: TextSegment[] = [];
		const fence = /```[^\n`]*\n?([\s\S]*?)```/g;
		let lastIndex = 0;
		let match: RegExpExecArray | null;
		while ((match = fence.exec(text)) !== null) {
			if (match.index > lastIndex) {
				segments.push({ type: 'text', content: text.slice(lastIndex, match.index) });
			}
			segments.push({ type: 'code', content: match[1].replace(/\n$/, '') });
			lastIndex = fence.lastIndex;
		}
		if (lastIndex < text.length) {
			segments.push({ type: 'text', content: text.slice(lastIndex) });
		}
		return segments;
	}

	const API_BASE = 'http://localhost:8000';
	const API_URL = `${API_BASE}/api/analyze`;

	let selectedFile: File | null = $state(null);
	let videoUrl = $state('');
	let uiState: UiState = $state('IDLE');
	let result: AnalyzeResponse | null = $state(null);
	let errorMessage: string | null = $state(null);
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

	// --- Dark mode ---
	let theme: 'light' | 'dark' = $state('light');

	function applyTheme(next: 'light' | 'dark') {
		theme = next;
		document.documentElement.setAttribute('data-theme', next);
		try {
			localStorage.setItem('theme', next);
		} catch {
			// localStorage unavailable - theme just won't persist
		}
	}

	function toggleTheme() {
		applyTheme(theme === 'dark' ? 'light' : 'dark');
	}

	onMount(() => {
		let stored: string | null = null;
		try {
			stored = localStorage.getItem('theme');
		} catch {
			// ignore
		}
		const prefersDark = window.matchMedia?.('(prefers-color-scheme: dark)').matches;
		applyTheme(stored === 'dark' || stored === 'light' ? stored : prefersDark ? 'dark' : 'light');
		loadDoneTopics();
	});

	// --- Mark topic as done ---
	let doneTopics = new SvelteSet<string>();

	function loadDoneTopics() {
		try {
			const raw = localStorage.getItem('done-topics');
			if (raw) for (const heading of JSON.parse(raw) as string[]) doneTopics.add(heading);
		} catch {
			// ignore
		}
	}

	function saveDoneTopics() {
		try {
			localStorage.setItem('done-topics', JSON.stringify([...doneTopics]));
		} catch {
			// ignore
		}
	}

	function toggleTopicDone(heading: string, event: Event) {
		event.stopPropagation();
		if (doneTopics.has(heading)) {
			doneTopics.delete(heading);
		} else {
			doneTopics.add(heading);
		}
		saveDoneTopics();
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

	// --- Search / filter roadmap ---
	let searchQuery = $state('');

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

	// --- Multi-language ---
	let targetLanguage = $state('');

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
			const response = await fetch(`${API_BASE}/api/topic/explain`, {
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
			const response = await fetch(`${API_BASE}/api/topic/quiz`, {
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
			const response = await fetch(`${API_BASE}/api/quiz/overall`, {
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

	let isDraggingFile = $state(false);

	function applyFile(file: File | null) {
		selectedFile = file;
		if (selectedFile) videoUrl = '';
		result = null;
		errorMessage = null;
		uiState = selectedFile ? 'FILE_SELECTED' : 'IDLE';
	}

	function handleFileChange(event: Event) {
		const input = event.target as HTMLInputElement;
		applyFile(input.files?.[0] ?? null);
	}

	function handleDragOver(event: DragEvent) {
		event.preventDefault();
		isDraggingFile = true;
	}

	function handleDragLeave() {
		isDraggingFile = false;
	}

	function handleDrop(event: DragEvent) {
		event.preventDefault();
		isDraggingFile = false;
		const file = event.dataTransfer?.files?.[0];
		if (file) applyFile(file);
	}

	function handleUrlInput(event: Event) {
		videoUrl = (event.target as HTMLInputElement).value;
		if (videoUrl) selectedFile = null;
		result = null;
		errorMessage = null;
		uiState = videoUrl ? 'FILE_SELECTED' : 'IDLE';
	}

	async function handleAnalyze() {
		if (!selectedFile && !videoUrl) return;

		uiState = 'PROCESSING';
		errorMessage = null;

		const formData = new FormData();
		if (selectedFile) {
			formData.append('file', selectedFile);
		} else {
			formData.append('url', videoUrl);
		}
		if (targetLanguage) formData.append('target_language', targetLanguage);

		try {
			const response = await fetch(API_URL, {
				method: 'POST',
				body: formData
			});

			const data = await response.json();

			if (!response.ok) {
				throw new Error(data.detail ?? 'Analysis failed');
			}

			result = data as AnalyzeResponse;
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
			searchQuery = '';
			uiState = 'SUCCESS';
		} catch (err) {
			errorMessage = err instanceof Error ? err.message : 'Something went wrong';
			uiState = 'ERROR';
		}
	}
</script>

<main>
	<button
		class="theme-toggle"
		aria-label={theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}
		onclick={toggleTheme}
	>
		{theme === 'dark' ? '☀️' : '🌙'}
	</button>

	<h1>AI Video Knowledge Extractor</h1>
	<p class="tagline">Turn any video into a structured, interactive learning roadmap.</p>

	<section
		class="card"
		class:drag-active={isDraggingFile}
		role="group"
		aria-label="Video upload area, drag and drop a file here"
		ondragover={handleDragOver}
		ondragleave={handleDragLeave}
		ondrop={handleDrop}
	>
		<h2>Upload a video</h2>

		<label class="choose-video">
			Choose Video
			<input type="file" accept="video/*" onchange={handleFileChange} />
		</label>

		{#if selectedFile}
			<p class="selected-file">
				Selected file:<br />
				<strong>{selectedFile.name}</strong>
			</p>
		{/if}

		<p class="or-divider">or</p>

		<div class="url-row">
			<input
				type="url"
				class="url-input"
				placeholder="Paste a YouTube / Google Drive / video link"
				value={videoUrl}
				oninput={handleUrlInput}
			/>

			<label class="language-select-label">
				Output language
				<select class="language-select" bind:value={targetLanguage}>
					<option value="">Auto</option>
					{#each Object.values(LANGUAGE_NAMES) as name}
						<option value={name}>{name}</option>
					{/each}
				</select>
			</label>
		</div>

		<button
			class="analyze-btn"
			disabled={uiState !== 'FILE_SELECTED' && uiState !== 'SUCCESS' && uiState !== 'ERROR'}
			onclick={handleAnalyze}
		>
			Analyze Video
		</button>

		{#if uiState === 'PROCESSING'}
			<p class="status"><span class="spinner"></span> Processing video... this may take a moment.</p>
		{/if}

		{#if uiState === 'ERROR' && errorMessage}
			<p class="error">{errorMessage}</p>
		{/if}
	</section>

	{#if uiState === 'SUCCESS' && result}
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

			<input
				type="search"
				class="topic-search"
				placeholder="Search roadmap topics…"
				bind:value={searchQuery}
			/>

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
						<button
							class="close-topic-btn"
							aria-label="Close topic"
							onclick={() => toggleTopic(topic.heading)}
						>
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
								<button
									class="ai-panel-close"
									aria-label="Close quiz"
									onclick={() => closeQuiz(topic.heading)}
								>
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
									<a
										class="resource-link"
										href={resourceHref(resource)}
										target="_blank"
										rel="noopener noreferrer"
									>
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
				<p class="roadmap-hint">
					Finished going through the roadmap? Test yourself across all of it.
				</p>

				{#if !overallQuiz}
					<button
						class="ai-action-btn overall-quiz-btn"
						disabled={overallQuizLoading}
						onclick={runOverallQuiz}
					>
						{overallQuizLoading ? 'Generating quiz…' : 'Take Full Quiz (10-15 questions)'}
					</button>
					{#if overallQuizError}
						<p class="ai-error">{overallQuizError}</p>
					{/if}
				{:else}
					{@const question = overallQuiz[overallQuizIndex]}
					{@const selected = overallQuizSelected.get(overallQuizIndex)}
					<div class="ai-panel overall-quiz-panel" transition:slide={{ duration: 200 }}>
						<button class="ai-panel-close" aria-label="Close quiz" onclick={closeOverallQuiz}>
							×
						</button>
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
								<button class="quiz-next-btn" onclick={nextOverallQuestion}>
									Next question →
								</button>
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
</main>

<style>
	:global(:root) {
		--page-bg-start: #fff7f4;
		--page-bg-end: #f4f6fb;
		--text-primary: #333;
		--text-secondary: #555;
		--text-muted: #888;
		--text-faint: #999;
		--border-color: #ddd;
		--border-soft: #eee;
		--surface: #fafafa;
		--surface-hover: #eee;
		--surface-alt: #f0f0f0;
		--card-bg: #fff;
		--tint-bg: #fff7f4;
		--tint-bg-strong: #fff0eb;
		--mix-light: white;
		--mix-dark: black;
	}

	:global(:root[data-theme='dark']) {
		--page-bg-start: #14141d;
		--page-bg-end: #1a1a24;
		--text-primary: #eaeaf0;
		--text-secondary: #b8b8c5;
		--text-muted: #8f8fa3;
		--text-faint: #7a7a8c;
		--border-color: #3a3a4a;
		--border-soft: #2c2c3a;
		--surface: #21212e;
		--surface-hover: #2a2a38;
		--surface-alt: #262633;
		--card-bg: #1c1c27;
		--tint-bg: rgba(255, 62, 0, 0.1);
		--tint-bg-strong: rgba(255, 62, 0, 0.16);
		--mix-light: #262633;
		--mix-dark: #f0f0f2;
	}

	:global(body) {
		background: linear-gradient(180deg, var(--page-bg-start) 0%, var(--page-bg-end) 100%);
		background-attachment: fixed;
		color: var(--text-primary);
	}

	main {
		max-width: 1400px;
		margin: 0 auto;
		padding: 3rem 1.25rem 4rem;
		font-family:
			system-ui,
			-apple-system,
			'Segoe UI',
			sans-serif;
		box-sizing: border-box;
	}

	h1 {
		font-size: clamp(1.9rem, 4vw, 2.1rem);
		margin: 0 auto 0.35rem;
		background: linear-gradient(100deg, #ff3e00 0%, #b45cd6 50%, #6b8afd 100%);
		background-clip: text;
		-webkit-background-clip: text;
		-webkit-text-fill-color: transparent;
		width: fit-content;
		text-align: center;
	}

	.results h2 {
		display: flex;
		align-items: center;
		gap: 0.5rem;
	}

	.results h2::before {
		content: '';
		display: inline-block;
		width: 0.5rem;
		height: 0.5rem;
		border-radius: 50%;
		background: linear-gradient(135deg, #ff3e00, #b45cd6);
	}

	main > h1,
	main > .tagline {
		text-align: center;
	}

	.tagline {
		color: var(--text-muted);
		margin: 0 0 2rem;
		font-size: 1rem;
	}

	.card {
		background: var(--card-bg);
		border-radius: 16px;
		box-shadow:
			0 1px 2px rgba(20, 20, 30, 0.04),
			0 8px 24px rgba(20, 20, 30, 0.06);
		padding: 2rem;
		box-sizing: border-box;
		border: 2px dashed transparent;
		transition:
			border-color 0.15s,
			background 0.15s;
	}

	.card.drag-active {
		border-color: #ff3e00;
		background: var(--tint-bg);
	}

	main > section:first-of-type {
		text-align: center;
	}

	.choose-video {
		display: inline-block;
		padding: 0.6rem 1.25rem;
		border: 1px solid var(--border-color);
		border-radius: 999px;
		cursor: pointer;
		margin-bottom: 1rem;
		font-weight: 500;
		transition:
			border-color 0.15s,
			background 0.15s;
	}

	.choose-video:hover {
		border-color: #ff3e00;
		background: var(--tint-bg);
	}

	.choose-video input[type='file'] {
		display: none;
	}

	.selected-file {
		margin: 1rem 0;
		color: var(--text-secondary);
	}

	.or-divider {
		color: #aaa;
		margin: 0.75rem 0;
		font-size: 0.85rem;
		text-transform: uppercase;
		letter-spacing: 0.08em;
	}

	.url-row {
		display: flex;
		align-items: flex-start;
		gap: 0.6rem;
		margin-bottom: 1.25rem;
	}

	.url-input {
		flex: 1;
		min-width: 0;
		width: 100%;
		box-sizing: border-box;
		padding: 0.75rem 1rem;
		border: 1px solid var(--border-color);
		border-radius: 10px;
		font-size: 0.95rem;
		transition:
			border-color 0.15s,
			box-shadow 0.15s;
	}

	.url-input:focus {
		outline: none;
		border-color: #ff3e00;
		box-shadow: 0 0 0 3px rgba(255, 62, 0, 0.12);
	}

	button {
		padding: 0.7rem 1.75rem;
		border-radius: 10px;
		border: none;
		background: #ff3e00;
		color: white;
		font-weight: 600;
		font-size: 0.95rem;
		cursor: pointer;
		transition:
			transform 0.1s,
			box-shadow 0.15s,
			background 0.15s;
	}

	button:hover:not(:disabled) {
		box-shadow: 0 4px 14px rgba(255, 62, 0, 0.3);
		transform: translateY(-1px);
	}

	button:active:not(:disabled) {
		transform: translateY(0);
	}

	button:disabled {
		background: var(--border-color);
		color: var(--text-faint);
		cursor: not-allowed;
	}

	.status {
		margin-top: 1.25rem;
		color: var(--text-secondary);
		display: flex;
		align-items: center;
		justify-content: center;
		gap: 0.6rem;
	}

	.spinner {
		width: 1rem;
		height: 1rem;
		border-radius: 50%;
		border: 2px solid #ffd7c7;
		border-top-color: #ff3e00;
		animation: spin 0.7s linear infinite;
	}

	@keyframes spin {
		to {
			transform: rotate(360deg);
		}
	}

	.error {
		margin-top: 1.25rem;
		color: #c0392b;
		background: #fdeeea;
		border-radius: 8px;
		padding: 0.6rem 0.9rem;
	}

	.results {
		margin-top: 2rem;
	}

	.intro {
		font-size: 1.05rem;
		color: var(--text-primary);
		line-height: 1.6;
		background: var(--tint-bg-strong);
		border-left: 4px solid #ff3e00;
		border-radius: 10px;
		padding: 1rem 1.25rem;
	}

	.key-points {
		list-style: none;
		margin: 0.5rem 0 1rem;
		padding: 0;
		display: flex;
		flex-direction: column;
		gap: 0.5rem;
	}

	.key-points li {
		color: var(--text-primary);
		line-height: 1.5;
		background: var(--surface);
		border-left: 4px solid var(--kp-color);
		border-radius: 8px;
		padding: 0.55rem 0.85rem;
		transition:
			transform 0.12s,
			box-shadow 0.12s;
	}

	.key-points li:hover {
		transform: translateX(3px);
		box-shadow: 0 2px 8px rgba(20, 20, 30, 0.06);
	}

	.key-points li:nth-child(5n + 1) {
		--kp-color: #ff3e00;
	}

	.key-points li:nth-child(5n + 2) {
		--kp-color: #6b8afd;
	}

	.key-points li:nth-child(5n + 3) {
		--kp-color: #2e9e5b;
	}

	.key-points li:nth-child(5n + 4) {
		--kp-color: #b45cd6;
	}

	.key-points li:nth-child(5n + 5) {
		--kp-color: #e0a800;
	}

	.explanation {
		color: var(--text-primary);
	}

	.example {
		display: flex;
		align-items: flex-start;
		justify-content: space-between;
		gap: 0.75rem;
		background: var(--surface);
		border-radius: 8px;
		padding: 0.6rem 0.85rem;
		line-height: 1.5;
	}

	.example p {
		margin: 0;
	}

	.copy-btn {
		flex: 0 0 auto;
		font-family: inherit;
		font-size: 0.75rem;
		padding: 0.25rem 0.6rem;
		border-radius: 6px;
		border: 1px solid var(--border-color);
		background: var(--card-bg);
		color: var(--text-secondary);
		cursor: pointer;
	}

	.copy-btn:hover {
		background: var(--surface-hover);
	}

	.roadmap {
		margin-top: 1rem;
	}

	.roadmap-node {
		position: relative;
		display: flex;
		gap: 1rem;
		padding-bottom: 2rem;
	}

	.roadmap-node:last-child {
		padding-bottom: 0;
	}

	.roadmap-node:not(:last-child)::before {
		content: '';
		position: absolute;
		left: 0.9375rem;
		top: 2rem;
		bottom: 0;
		width: 2px;
		background: linear-gradient(180deg, #ffcbb3, var(--border-color) 80%);
	}

	.node-marker {
		flex: 0 0 auto;
		width: 2rem;
		height: 2rem;
		border-radius: 50%;
		background: var(--heading-color, #ff3e00);
		color: white;
		display: flex;
		align-items: center;
		justify-content: center;
		font-weight: 600;
		font-size: 0.9rem;
		z-index: 1;
		box-shadow: 0 2px 6px color-mix(in srgb, var(--heading-color, #ff3e00) 45%, transparent);
		transition:
			transform 0.15s,
			box-shadow 0.15s;
	}

	.node-marker.marker-active {
		transform: scale(1.15);
		box-shadow: 0 3px 10px rgba(255, 62, 0, 0.5);
	}

	.node-body {
		flex: 1;
		min-width: 0;
	}

	.roadmap-hint {
		color: var(--text-faint);
		font-size: 0.85rem;
		margin: 0.25rem 0 1rem;
	}

	.node-box {
		display: inline-block;
		max-width: 100%;
		white-space: normal;
		padding: 0.5rem 1rem;
		border-radius: 10px;
		font-weight: 600;
		margin-bottom: 0.5rem;
		font-family: inherit;
		cursor: pointer;
		transition:
			filter 0.15s,
			box-shadow 0.15s,
			transform 0.1s;
		box-shadow: 0 1px 2px rgba(20, 20, 30, 0.04);
	}

	.node-box:hover {
		filter: brightness(0.96);
		box-shadow: 0 3px 8px rgba(20, 20, 30, 0.08);
		transform: translateY(-1px);
	}

	.node-box.main {
		background: color-mix(in srgb, var(--heading-color, #ff3e00) 12%, var(--mix-light));
		border: 1px solid var(--heading-color, #ff3e00);
		color: color-mix(in srgb, var(--heading-color, #ff3e00) 75%, var(--mix-dark));
	}

	.roadmap-node:nth-child(5n + 1) {
		--heading-color: #ff3e00;
	}

	.roadmap-node:nth-child(5n + 2) {
		--heading-color: #6b8afd;
	}

	.roadmap-node:nth-child(5n + 3) {
		--heading-color: #2e9e5b;
	}

	.roadmap-node:nth-child(5n + 4) {
		--heading-color: #b45cd6;
	}

	.roadmap-node:nth-child(5n + 5) {
		--heading-color: #e0a800;
	}

	.node-box.sub {
		background: color-mix(in srgb, var(--sub-color, #8b5cf6) 10%, var(--mix-light));
		border: 1px solid var(--sub-color, #8b5cf6);
		color: color-mix(in srgb, var(--sub-color, #8b5cf6) 75%, var(--mix-dark));
		font-size: 0.9rem;
	}

	.branch:nth-child(3n + 1) {
		--sub-color: #8b5cf6;
	}

	.branch:nth-child(3n + 2) {
		--sub-color: #2596be;
	}

	.branch:nth-child(3n + 3) {
		--sub-color: #d6336c;
	}

	.node-box.expanded {
		box-shadow: 0 0 0 3px color-mix(in srgb, var(--heading-color, #ff3e00) 30%, transparent);
	}

	.node-box.sub.expanded {
		box-shadow: 0 0 0 3px color-mix(in srgb, var(--sub-color, #8b5cf6) 30%, transparent);
	}

	.node-details {
		position: relative;
		margin-bottom: 0.75rem;
		background: #fcfcfd;
		border: 1px solid var(--border-soft);
		border-radius: 12px;
		padding: 2.5rem 1.25rem 1rem;
	}

	.related {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 0.4rem;
		margin-top: 0.75rem;
	}

	.related-label {
		color: var(--text-muted);
		font-size: 0.85rem;
	}

	.related-link {
		font-family: inherit;
		font-size: 0.8rem;
		background: var(--surface-alt);
		border: 1px solid var(--border-color);
		border-radius: 999px;
		padding: 0.2rem 0.7rem;
		cursor: pointer;
		color: #444;
	}

	.related-link:hover {
		background: var(--surface-hover);
	}

	.branches {
		margin-top: 1rem;
		margin-left: 1rem;
		padding-left: 1rem;
		border-left: 2px dashed var(--border-color);
		display: flex;
		flex-direction: column;
		gap: 1rem;
	}

	.close-topic-btn {
		font-family: inherit;
		position: absolute;
		top: 0.85rem;
		right: 0.9rem;
		width: 1.75rem;
		height: 1.75rem;
		line-height: 1;
		padding: 0;
		border-radius: 50%;
		border: 1px solid var(--border-color);
		background: var(--card-bg);
		color: var(--text-muted);
		font-size: 1.1rem;
		cursor: pointer;
	}

	.close-topic-btn:hover {
		background: var(--surface-hover);
		color: var(--text-primary);
	}

	.ai-actions {
		display: flex;
		align-items: center;
		gap: 0.6rem;
		margin: 1rem 0 0.5rem;
	}

	.ai-actions-label {
		font-size: 0.8rem;
		color: var(--text-muted);
		text-transform: uppercase;
		letter-spacing: 0.03em;
	}

	.ai-action-btn {
		font-family: inherit;
		font-size: 0.8rem;
		padding: 0.3rem 0.8rem;
		border-radius: 6px;
		border: 1px solid #ff3e00;
		background: var(--card-bg);
		color: #ff3e00;
		cursor: pointer;
	}

	.ai-action-btn:hover {
		background: var(--tint-bg-strong);
	}

	.ai-loading {
		color: var(--text-faint);
		font-size: 0.9rem;
		font-style: italic;
		margin-top: 0.5rem;
	}

	.ai-error {
		color: #c53000;
		font-size: 0.85rem;
		margin-top: 0.5rem;
	}

	.ai-panel {
		position: relative;
		margin-top: 0.75rem;
		background: var(--surface);
		border: 1px solid var(--border-soft);
		border-radius: 8px;
		padding: 0.75rem 2.25rem 0.75rem 1rem;
	}

	.ai-panel-close {
		font-family: inherit;
		position: absolute;
		top: 0.6rem;
		right: 0.6rem;
		width: 1.5rem;
		height: 1.5rem;
		line-height: 1;
		padding: 0;
		border-radius: 50%;
		border: 1px solid var(--border-color);
		background: var(--card-bg);
		color: var(--text-muted);
		font-size: 1rem;
		cursor: pointer;
	}

	.ai-panel-close:hover {
		background: var(--surface-hover);
		color: var(--text-primary);
	}

	.ai-panel strong {
		display: block;
		font-size: 0.8rem;
		text-transform: uppercase;
		letter-spacing: 0.03em;
		color: var(--text-muted);
		margin-bottom: 0.4rem;
	}

	.ai-panel-hint {
		font-size: 0.75rem;
		color: var(--text-faint);
		margin: 0 0 0.6rem;
	}

	.explain-points {
		list-style: none;
		margin: 0;
		padding: 0;
		display: flex;
		flex-direction: column;
		gap: 0.4rem;
	}

	.explain-point-toggle {
		width: 100%;
		display: flex;
		align-items: center;
		gap: 0.5rem;
		font-family: inherit;
		font-size: 0.9rem;
		font-weight: 600;
		text-align: left;
		padding: 0.55rem 0.75rem;
		border-radius: 8px;
		border: 1px solid var(--border-soft);
		background: var(--card-bg);
		color: var(--text-primary);
		cursor: pointer;
		transition:
			background 0.12s,
			border-color 0.12s;
	}

	.explain-point-toggle:hover {
		background: var(--surface);
		border-color: var(--border-color);
	}

	.explain-point-toggle.open {
		border-color: #ff3e00;
		background: var(--tint-bg);
	}

	.explain-point-chevron {
		display: inline-block;
		flex: 0 0 auto;
		color: #ff3e00;
		transition: transform 0.15s;
	}

	.explain-point-toggle.open .explain-point-chevron {
		transform: rotate(90deg);
	}

	.explain-point-detail {
		margin: 0.35rem 0 0;
		padding: 0.6rem 0.85rem;
		font-size: 0.88rem;
		color: var(--text-secondary);
		line-height: 1.5;
		background: var(--surface);
		border-radius: 8px;
	}

	.quiz-options {
		display: flex;
		flex-direction: column;
		gap: 0.4rem;
		margin-top: 0.5rem;
	}

	.quiz-option {
		font-family: inherit;
		text-align: left;
		font-size: 0.9rem;
		padding: 0.5rem 0.75rem;
		border-radius: 6px;
		border: 1px solid var(--border-color);
		background: var(--card-bg);
		color: var(--text-primary);
		cursor: pointer;
	}

	.quiz-option:hover:not(:disabled) {
		background: var(--surface-hover);
	}

	.quiz-option:disabled {
		cursor: default;
	}

	.quiz-option.correct {
		border-color: #2e7d32;
		background: #eaf6ea;
		color: #2e7d32;
	}

	.quiz-option.incorrect {
		border-color: #c53000;
		background: #fdeeea;
		color: #c53000;
	}

	.quiz-explanation {
		margin-top: 0.6rem;
		font-size: 0.9rem;
		color: var(--text-secondary);
	}

	.quiz-question {
		font-size: 0.95rem;
		color: var(--text-primary);
	}

	.quiz-code {
		margin: 0.4rem 0;
		padding: 0.6rem 0.75rem;
		background: #1e1e2e;
		color: #f2f2f2;
		border-radius: 6px;
		font-family: ui-monospace, 'SFMono-Regular', Menlo, Consolas, monospace;
		font-size: 0.82rem;
		line-height: 1.5;
		overflow-x: auto;
		white-space: pre;
	}

	.quiz-option .quiz-code {
		margin: 0.3rem 0 0;
	}

	.quiz-header {
		display: flex;
		align-items: baseline;
		justify-content: space-between;
		gap: 0.5rem;
	}

	.quiz-progress {
		font-size: 0.75rem;
		color: var(--text-faint);
		text-transform: none;
		letter-spacing: normal;
	}

	.quiz-next-btn {
		font-family: inherit;
		margin-top: 0.75rem;
		font-size: 0.85rem;
		padding: 0.45rem 1rem;
		border-radius: 8px;
		border: none;
		background: #ff3e00;
		color: white;
		cursor: pointer;
	}

	.quiz-next-btn:hover {
		box-shadow: 0 3px 10px rgba(255, 62, 0, 0.3);
	}

	.quiz-done {
		margin-top: 0.75rem;
		font-size: 0.85rem;
		color: #2e9e5b;
		font-weight: 600;
	}

	.resources {
		margin-top: 1rem;
		background: var(--surface);
		border: 1px solid var(--border-soft);
		border-radius: 8px;
		padding: 0.75rem 1rem;
	}

	.resources strong {
		display: block;
		font-size: 0.8rem;
		text-transform: uppercase;
		letter-spacing: 0.03em;
		color: var(--text-muted);
		margin-bottom: 0.5rem;
	}

	.resource-link {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		font-size: 0.9rem;
		color: #3454c9;
		text-decoration: none;
		padding: 0.25rem 0;
	}

	.resource-link:hover {
		text-decoration: underline;
	}

	.overall-quiz-section {
		margin-top: 2.5rem;
		padding-top: 1.75rem;
		border-top: 2px dashed var(--border-soft);
		text-align: center;
	}

	.overall-quiz-btn {
		margin-top: 0.5rem;
	}

	.overall-quiz-panel {
		max-width: 46rem;
		width: 100%;
		margin: 0.75rem auto 0;
		text-align: left;
	}

	/* --- Dark mode toggle --- */
	.theme-toggle {
		position: fixed;
		top: 1.25rem;
		right: 1.25rem;
		width: 2.5rem;
		height: 2.5rem;
		padding: 0;
		border-radius: 50%;
		background: var(--card-bg);
		border: 1px solid var(--border-color);
		font-size: 1.15rem;
		line-height: 1;
		box-shadow: 0 2px 8px rgba(20, 20, 30, 0.1);
		z-index: 10;
	}

	.theme-toggle:hover:not(:disabled) {
		transform: none;
		box-shadow: 0 2px 10px rgba(20, 20, 30, 0.16);
	}

	/* --- Output language select --- */
	.language-select-label {
		flex: 0 0 auto;
		display: block;
		text-align: left;
		font-size: 0.7rem;
		color: var(--text-muted);
		white-space: nowrap;
	}

	.language-select {
		display: block;
		margin-top: 0.3rem;
		padding: 0.4rem 0.5rem;
		border-radius: 8px;
		border: 1px solid var(--border-color);
		background: var(--card-bg);
		color: var(--text-primary);
		font-size: 0.78rem;
		font-family: inherit;
		box-sizing: border-box;
	}

	/* --- Detected language badge --- */
	.language-badge {
		display: inline-block;
		font-size: 0.75rem;
		color: var(--text-muted);
		background: var(--surface);
		border: 1px solid var(--border-soft);
		border-radius: 999px;
		padding: 0.2rem 0.7rem;
		margin-bottom: 0.75rem;
	}

	/* --- Progress bar --- */
	.progress-wrap {
		margin: 1rem 0;
	}

	.progress-label {
		display: flex;
		justify-content: space-between;
		font-size: 0.8rem;
		color: var(--text-muted);
		margin-bottom: 0.35rem;
	}

	.progress-bar {
		height: 0.5rem;
		border-radius: 999px;
		background: var(--surface-hover);
		overflow: hidden;
	}

	.progress-fill {
		height: 100%;
		background: linear-gradient(90deg, #ff3e00, #b45cd6);
		border-radius: 999px;
		transition: width 0.2s;
	}

	/* --- Topic search --- */
	.topic-search {
		width: 100%;
		box-sizing: border-box;
		padding: 0.6rem 0.9rem;
		border: 1px solid var(--border-color);
		border-radius: 10px;
		background: var(--card-bg);
		color: var(--text-primary);
		font-size: 0.9rem;
		font-family: inherit;
		margin: 0.5rem 0 1rem;
	}

	/* --- Mark topic as done --- */
	.done-checkbox {
		display: inline-flex;
		align-items: center;
		gap: 0.4rem;
		font-size: 0.8rem;
		color: var(--text-secondary);
		margin-bottom: 0.75rem;
		cursor: pointer;
	}

	.done-checkbox input {
		cursor: pointer;
	}

	/* --- Quiz difficulty badge --- */
	.difficulty-badge {
		display: inline-block;
		font-size: 0.7rem;
		font-weight: 600;
		text-transform: uppercase;
		letter-spacing: 0.03em;
		padding: 0.15rem 0.55rem;
		border-radius: 999px;
		margin: 0.4rem 0 0.2rem;
	}

	.difficulty-easy {
		background: #eaf6ea;
		color: #2e7d32;
	}

	.difficulty-medium {
		background: #fff4e0;
		color: #b06f00;
	}

	.difficulty-hard {
		background: #fdeeea;
		color: #c53000;
	}

	@media (max-width: 640px) {
		main {
			padding: 1.75rem 0.85rem 3rem;
		}

		.card {
			padding: 1.25rem;
			border-radius: 12px;
		}

		.choose-video,
		.url-input,
		.analyze-btn {
			width: 100%;
			box-sizing: border-box;
		}

		.url-row {
			flex-direction: column;
			align-items: stretch;
		}

		.language-select {
			width: 100%;
		}

		.analyze-btn {
			padding: 0.75rem 1.25rem;
		}

		.roadmap-node {
			gap: 0.65rem;
		}

		.node-marker {
			width: 1.65rem;
			height: 1.65rem;
			font-size: 0.8rem;
		}

		.roadmap-node:not(:last-child)::before {
			left: 0.78rem;
		}

		.node-details {
			padding: 2.25rem 1rem 0.85rem;
		}

		.example {
			flex-direction: column;
			align-items: flex-start;
		}

		.copy-btn {
			align-self: flex-end;
		}

		.ai-actions {
			flex-wrap: wrap;
		}

		.branches {
			margin-left: 0.5rem;
			padding-left: 0.75rem;
		}
	}
</style>
