// Minimal Next.js page — redirects to the main HTML landing
// This exists so Vercel recognizes this as a Next.js project

export default function Home() {
  // This component never renders — Vercel redirects static files
  return null;
}

// Force SSR so Vercel doesn't pre-render (the HTML is already in the root)
export async function getServerSideProps() {
  return { props: {} };
}
