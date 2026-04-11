import { BrowserRouter, Routes, Route, NavLink } from "react-router-dom";
import Dashboard from "./pages/Dashboard";
import TradeHistory from "./pages/TradeHistory";
import Analysis from "./pages/Analysis";
import Statistics from "./pages/Statistics";
import Settings from "./pages/Settings";

function App() {
  return (
    <BrowserRouter>
      <nav className="nav">
        <span className="nav-brand">AutoTrader</span>
        <NavLink to="/" end>Dashboard</NavLink>
        <NavLink to="/trades">Trades</NavLink>
        <NavLink to="/analysis">Analysis</NavLink>
        <NavLink to="/stats">Statistics</NavLink>
        <NavLink to="/settings">Settings</NavLink>
      </nav>
      <Routes>
        <Route path="/" element={<Dashboard />} />
        <Route path="/trades" element={<TradeHistory />} />
        <Route path="/analysis" element={<Analysis />} />
        <Route path="/stats" element={<Statistics />} />
        <Route path="/settings" element={<Settings />} />
      </Routes>
    </BrowserRouter>
  );
}
export default App;
