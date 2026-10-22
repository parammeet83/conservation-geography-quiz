import { Link, Route, Routes } from "react-router-dom";
import HomePage from "./pages/HomePage";
import QuizPage from "./pages/QuizPage";
import ResultPage from "./pages/ResultPage";

export default function App() {
  return (
    <>
      <a className="skip-link" href="#main">
        Skip to content
      </a>
      <header className="site-header">
        <div className="container site-header__inner">
          <Link to="/" className="brand">
            Conservation Geography Quiz
          </Link>
        </div>
      </header>
      <main id="main" className="container" tabIndex={-1}>
        <Routes>
          <Route path="/" element={<HomePage />} />
          <Route path="/attempts/:attemptId" element={<QuizPage />} />
          <Route path="/attempts/:attemptId/result" element={<ResultPage />} />
          <Route path="*" element={<NotFound />} />
        </Routes>
      </main>
    </>
  );
}

function NotFound() {
  return (
    <section className="panel">
      <h1>Page not found</h1>
      <p>
        <Link to="/">Back to quiz selection</Link>
      </p>
    </section>
  );
}
