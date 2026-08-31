export const LANGUAGE_NAMES: Record<string, string> = {
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

export function languageLabel(code: string) {
	return LANGUAGE_NAMES[code] ?? code.toUpperCase();
}
