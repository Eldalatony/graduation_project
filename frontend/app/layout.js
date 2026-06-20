export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <head>
        <meta name="viewport" content="width=device-width, initial-scale=1" />
        <title>SHEMMS</title>
      </head>
      <body style={{ margin: 0, padding: 0, background: '#f0f4ff' }}>{children}</body>
    </html>
  );
}
