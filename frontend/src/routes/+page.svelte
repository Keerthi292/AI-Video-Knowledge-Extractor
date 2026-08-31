<script lang="ts">
	import { goto } from '$app/navigation';
	import { auth } from '$lib/auth.svelte';
	import { LANGUAGE_NAMES } from '$lib/languages';
	import type { AnalyzeResponse } from '$lib/types';

	type UiState = 'IDLE' | 'FILE_SELECTED' | 'PROCESSING' | 'ERROR';

	let selectedFile: File | null = $state(null);
	let videoUrl = $state('');
	let targetLanguage = $state('');
	let uiState: UiState = $state('IDLE');
	let errorMessage: string | null = $state(null);
	let isDraggingFile = $state(false);

	function applyFile(file: File | null) {
		selectedFile = file;
		if (selectedFile) videoUrl = '';
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
			const response = await auth.fetch('/api/analyze', {
				method: 'POST',
				body: formData
			});

			const data = await response.json();

			if (!response.ok) {
				throw new Error(data.detail ?? 'Analysis failed');
			}

			const result = data as AnalyzeResponse;
			await goto(`/analysis/${result.id}`);
		} catch (err) {
			errorMessage = err instanceof Error ? err.message : 'Something went wrong';
			uiState = 'ERROR';
		}
	}
</script>

<section
	class="card upload-card"
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
		disabled={uiState !== 'FILE_SELECTED' && uiState !== 'ERROR'}
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
