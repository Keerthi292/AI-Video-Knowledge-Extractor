import type { TextSegment } from './types';

export function parseCodeSegments(text: string): TextSegment[] {
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
