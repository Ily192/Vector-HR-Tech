import React, { useState, useEffect, createContext, useContext } from 'react';
import { HashRouter, Routes, Route, Navigate } from 'react-router-dom';
import { supabase } from './services/supabaseClient';
import { dataService } from './services/dataService';
import { User } from './types';

import Login from './pages/Login';
import Dashboard from './pages/Dashboard';
import Requests from './pages/Requests';
import Profile from './pages/Profile';
import CompleteProfileForm from './pages/CompleteProfileForm';
import Sidebar from './components/Sidebar';
import { Menu, X } from 'lucide-react';

interface AuthContextType {
  user: User | null;
  needsProfile: boolean;
  checkAuth: () => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth debe usarse dentro de AuthProvider");
  return context;
};

const Layout: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [sidebarOpen, setSidebarOpen] = useState(false);
  return (
    <div className="flex h-screen bg-gray-50 overflow-hidden">
      <div className={`fixed inset-y-0 left-0 z-30 w-64 bg-slate-900 text-white transform transition-transform lg:relative lg:translate-x-0 ${sidebarOpen ? 'translate-x-0' : '-translate-x-full'}`}>
        <div className="p-6 flex justify-between items-center">
          <span className="font-bold text-xl">PORTAL</span>
          <button className="lg:hidden" onClick={() => setSidebarOpen(false)}><X /></button>
        </div>
        <Sidebar />
      </div>
      <div className="flex-1 flex flex-col overflow-hidden">
        <header className="bg-white p-4 lg:hidden flex items-center shadow-sm">
          <button onClick={() => setSidebarOpen(true)}><Menu /></button>
          <span className="ml-4 font-bold">Disruptive Talent</span>
        </header>
        <main className="flex-1 overflow-y-auto p-4 md:p-8">{children}</main>
      </div>
    </div>
  );
};

export default function App() {
  const [user, setUser] = useState<User | null>(null);
  const [needsProfile, setNeedsProfile] = useState(false);
  const [loading, setLoading] = useState(true);

  const checkAuth = async () => {
    setLoading(true);
    try {
      const res = await dataService.getCurrentProfile();
      setUser(res.user);
      setNeedsProfile(res.needsProfile);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    checkAuth();
    const { data: { subscription } } = supabase.auth.onAuthStateChange(() => checkAuth());
    return () => subscription.unsubscribe();
  }, []);

  if (loading) return <div className="h-screen flex items-center justify-center">Cargando...</div>;

  return (
    <AuthContext.Provider value={{ user, needsProfile, checkAuth, logout: () => supabase.auth.signOut() }}>
      <HashRouter>
        <Routes>
          <Route path="/login" element={!user && !needsProfile ? <Login /> : <Navigate to="/" />} />
          <Route path="/completar-registro" element={needsProfile ? <CompleteProfileForm /> : <Navigate to="/" />} />
          
          <Route path="/dashboard" element={user ? <Layout><Dashboard /></Layout> : <Navigate to="/" />} />
          <Route path="/requests" element={user ? <Layout><Requests /></Layout> : <Navigate to="/" />} />
          <Route path="/profile" element={user ? <Layout><Profile /></Layout> : <Navigate to="/" />} />

          <Route path="/" element={
            user ? <Navigate to="/dashboard" /> : (needsProfile ? <Navigate to="/completar-registro" /> : <Navigate to="/login" />)
          } />
          <Route path="*" element={<Navigate to="/" />} />
        </Routes>
      </HashRouter>
    </AuthContext.Provider>
  );
}
