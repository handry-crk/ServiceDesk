export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        cream: '#ECE4D4', brick: { DEFAULT: '#B42F27', dark: '#8E231D', soft: '#F4DCD8' },
        ink: '#2B2522', line: '#D9CFBD', ok: '#2E7D4F', warn: '#C98A1B', mute: '#8A8178',
      },
      fontFamily: { sans: ['"Plus Jakarta Sans"', 'system-ui', 'sans-serif'] },
    },
  },
}
