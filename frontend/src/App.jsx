import { BrowserRouter, Routes, Route, Link, useLocation } from "react-router-dom";
import Home from "./pages/Home";
import Demo from "./pages/Demo";
import Pilot from "./pages/Pilot";

function Nav() {
  const location = useLocation();

  const links = [
    { to: "/", label: "Home" },
    { to: "/demo", label: "Demo" },
    { to: "/pilot", label: "Pilot" },
  ];

  return (
    <nav className="fixed top-0 left-0 right-0 z-50 border-b border-deep-azure/40 px-6 py-2 flex items-center gap-6"
         style={{ background: "rgba(12, 24, 36, 0.92)", backdropFilter: "blur(12px)" }}>

      {/* Official logo */}
      <Link to="/" className="flex-shrink-0">
        <img
          src="/logo-dark.png"
          alt="Babylon∞n.ai"
          className="h-8 w-auto"
        />
      </Link>

      {/* Nav links */}
      <div className="flex gap-5 ml-2">
        {links.map((l) => (
          <Link
            key={l.to}
            to={l.to}
            className={`text-sm font-sans transition-colors ${
              location.pathname === l.to
                ? "text-babylonian-gold font-semibold"
                : "text-muted-blue hover:text-silver"
            }`}
          >
            {l.label}
          </Link>
        ))}
      </div>

      {/* Patent badge */}
      <div className="ml-auto text-xs font-mono text-deep-azure/70 hidden sm:block">
        PCT/IB2026/053131
      </div>
    </nav>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <Nav />
      <div className="pt-14">
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/demo" element={<Demo />} />
          <Route path="/pilot" element={<Pilot />} />
          {/* Legacy redirect */}
          <Route path="/syaivo" element={<Pilot />} />
        </Routes>
      </div>
    </BrowserRouter>
  );
}
