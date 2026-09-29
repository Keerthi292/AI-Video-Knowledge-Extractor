<script lang="ts">
	import { page } from '$app/state';
	import { SvelteSet } from 'svelte/reactivity';
	import { slide } from 'svelte/transition';
	import { API_BASE } from '$lib/api';
	import { languageLabel } from '$lib/languages';
	import type { SharedAnalysis, Topic, Resource } from '$lib/types';

	let shareToken = $derived(page.params.token);

	let loading = $state(true);
	let loadError: string | null = $state(null);
	let result: SharedAnalysis | null = $state(null);
	let expandedTopics = new SvelteSet<string>();

	$effect(() => {
		const token = shareToken;
		loading = true;
		loadError = null;
		result = null;
		expandedTopics.clear();

		(async () => {
			try {
				// Public endpoint - deliberately a plain fetch, not auth.fetch.
				const response = await fetch(`${API_BASE}/api/shared/${encodeURIComponent(token ?? '')}`);
				const data = await response.json();
				if (!response.ok) {
					throw new Error(
						response.status === 404
							? 'This link is no longer shared, or it never existed.'
							: (data.detail ?? 'Failed to load this roadmap')
					);
				}
				result = data as SharedAnalysis;
			} catch (err) {
				loadError = err instanceof Error ? err.message : 'Something went wrong';
			} finally {
				loading = false;
			}
		})();
	});

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
</script>

<svelte:head>
	<title>{result ? `${result.source} — Shared roadmap` : 'Shared roadmap'}</title>
</svelte:head>

<a class="back-link" href="/">← Make your own roadmap</a>

{#if loading}
	<p class="status"><span class="spinner"></span> Loading shared roadmap…</p>
{:else if loadError}
	<p class="error">{loadError}</p>
{:else if result}
	<section class="results card">
		<div class="results-header">
			<span class="language-badge">Shared roadmap · {result.source}</span>
			{#if result.detected_language}
				<span class="language-badge">Detected language: {languageLabel(result.detected_language)}</span>
			{/if}
		</div>

		<p class="intro">{result.intro}</p>

		<h2>Key Points</h2>
		<ul class="key-points">
			{#each result.key_points as point}
				<li>{point}</li>
			{/each}
		</ul>

		{#snippet topicDetails(topic: Topic)}
			{#if expandedTopics.has(topic.heading)}
				<div class="node-details" transition:slide={{ duration: 200 }}>
					<button class="close-topic-btn" aria-label="Close topic" onclick={() => toggleTopic(topic.heading)}>
						×
					</button>

					<p class="explanation">{topic.content}</p>
					{#if topic.example}
						<div class="example">
							<p><strong>Example:</strong> {topic.example}</p>
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
		<div class="roadmap">
			{#each result.roadmap as topic, i}
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
			<p class="roadmap-hint">
				Want AI explanations and quizzes for this? Turn any video into a roadmap like this one.
			</p>
			<a class="ai-action-btn" href="/">Try it free →</a>
		</div>
	</section>
{/if}
