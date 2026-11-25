import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import DashboardPage from './pages/DashboardPage'
import LandingPage from './pages/LandingPage'
import CaseFilePage from './pages/CaseFilePage'
import ReconstructionPage from './pages/ReconstructionPage'
import InvestigationPage from './pages/InvestigationPage'

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<LandingPage />} />
        <Route path="/dashboard" element={<DashboardPage />} />
        <Route path="/welcome" element={<LandingPage />} />
        <Route path="/case/new" element={<CaseFilePage />} />
        <Route path="/reconstruction" element={<ReconstructionPage />} />
        <Route path="/investigation" element={<InvestigationPage />} />
        <Route path="*" element={<Navigate to="/dashboard" replace />} />
      </Routes>
    </BrowserRouter>
  )
}

export default App
