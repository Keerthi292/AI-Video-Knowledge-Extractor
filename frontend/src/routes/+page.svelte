<script lang="ts">
	type UiState = 'IDLE' | 'FILE_SELECTED' | 'PROCESSING' | 'SUCCESS' | 'ERROR';

	type AnalyzeResponse = {
		success: boolean;
		summary: string;
		key_points: string[];
		transcript: string;
	};

	const API_URL = 'http://localhost:8000/api/analyze';

	let selectedFile: File | null = $state(null);
	let uiState: UiState = $state('IDLE');
	let result: AnalyzeResponse | null = $state(null);
	let errorMessage: string | null = $state(null);

	function handleFileChange(event: Event) {
		const input = event.target as HTMLInputElement;
		selectedFile = input.files?.[0] ?? null;
		result = null;
		errorMessage = null;
		uiState = selectedFile ? 'FILE_SELECTED' : 'IDLE';
	}

	async function handleAnalyze() {
		if (!selectedFile) return;

		uiState = 'PROCESSING';
		errorMessage = null;

		const formData = new FormData();
		formData.append('file', selectedFile);

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
			uiState = 'SUCCESS';
		} catch (err) {
			errorMessage = err instanceof Error ? err.message : 'Something went wrong';
			uiState = 'ERROR';
		}
	}
</script>

<main>
	<h1>AI Video Knowledge Extractor</h1>

	<section>
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

		<button
			disabled={uiState !== 'FILE_SELECTED' && uiState !== 'SUCCESS' && uiState !== 'ERROR'}
			onclick={handleAnalyze}
		>
			Analyze Video
		</button>

		{#if uiState === 'PROCESSING'}
			<p class="status">Processing video... this may take a moment.</p>
		{/if}

		{#if uiState === 'ERROR' && errorMessage}
			<p class="error">{errorMessage}</p>
		{/if}
	</section>

	{#if uiState === 'SUCCESS' && result}
		<section class="results">
			<h2>Summary</h2>
			<hr />
			<p>{result.summary}</p>

			<h2>Key Points</h2>
			<hr />
			<ul>
				{#each result.key_points as point}
					<li>{point}</li>
				{/each}
			</ul>

			<h2>Transcript</h2>
			<hr />
			<p class="transcript">{result.transcript}</p>
		</section>
	{/if}
</main>

<style>
	main {
		max-width: 640px;
		margin: 4rem auto;
		font-family: system-ui, sans-serif;
		padding: 0 1rem;
	}

	main > section:first-of-type {
		text-align: center;
	}

	.choose-video {
		display: inline-block;
		padding: 0.5rem 1rem;
		border: 1px solid #ccc;
		border-radius: 6px;
		cursor: pointer;
		margin-bottom: 1rem;
	}

	.choose-video input[type='file'] {
		display: none;
	}

	.selected-file {
		margin: 1rem 0;
	}

	button {
		padding: 0.6rem 1.5rem;
		border-radius: 6px;
		border: none;
		background: #ff3e00;
		color: white;
		cursor: pointer;
	}

	button:disabled {
		background: #ccc;
		cursor: not-allowed;
	}

	.status {
		margin-top: 1rem;
		color: #555;
	}

	.error {
		margin-top: 1rem;
		color: #c0392b;
	}

	.results {
		margin-top: 2.5rem;
	}

	.results h2 {
		margin-bottom: 0.25rem;
	}

	.results hr {
		border: none;
		border-top: 1px solid #ddd;
		margin-bottom: 0.75rem;
	}

	.transcript {
		white-space: pre-wrap;
		color: #333;
	}
</style>
