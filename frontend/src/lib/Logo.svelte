<script lang="ts">
	/** The app mark: play button over three roadmap nodes. */
	let { class: className = '' }: { class?: string } = $props();

	// Unique per instance so two logos on screen never share a gradient id.
	const uid = $props.id();
	const gradientId = `logo-gradient-${uid}`;
</script>

<svg class="logo {className}" viewBox="0 0 64 64" aria-hidden="true">
	<defs>
		<linearGradient id={gradientId} x1="0" y1="0" x2="1" y2="1">
			<stop offset="0%" stop-color="#ff3e00" />
			<stop offset="100%" stop-color="#b45cd6" />
		</linearGradient>
	</defs>
	<rect x="4" y="4" width="56" height="56" rx="16" fill="url(#{gradientId})" />
	<path d="M26 20 L46 32 L26 44 Z" fill="white" />
	<circle class="node node-1" cx="15" cy="50" r="3" fill="white" />
	<circle class="node node-2" cx="32" cy="54" r="3" fill="white" />
	<circle class="node node-3" cx="49" cy="50" r="3" fill="white" />
</svg>
