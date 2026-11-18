import './globals.css';

export const metadata = {
  title: 'Clipper',
  description: 'Turn one long video into vertical clips with captions.',
};

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
