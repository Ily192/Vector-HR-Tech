import React from 'react';
import { NavLink } from 'react-router-dom';
import { LayoutDashboard, FileText, User, LogOut } from 'lucide-react';
import { useAuth } from '../App';

export default function Sidebar() {
  const { logout, user } = useAuth();

  const navClass = ({ isActive }: { isActive: boolean }) =>
    `flex items-center space-x-3 px-6 py-3 transition-all duration-200 border-l-4 ${
      isActive 
        ? 'bg-brand-secondary/50 border-brand-primary text-brand-primary' 
        : 'border-transparent text-gray-400 hover:text-white hover:bg-white/5'
    }`;

  return (
    <div className="flex flex-col h-full bg-brand-secondary text-white">
      {/* Brand Header */}
      <div className="p-6 hidden lg:block border-b border-gray-700/50">
        <div className="flex items-center space-x-3 mb-2">
          {/* Logo del cliente */}
          <img src="portal-hr-TH-vercel/Public/icon_light.png" alt="Disruptive Logo" className="h-10 w-auto object-contain" />
          <div className="flex flex-col">
            <span className="text-xl font-bold tracking-tight leading-tight">disruptive</span>
            <span className="text-sm font-light tracking-wide text-brand-primary leading-none">talent</span>
          </div>
        </div>
      </div>

      <nav className="flex-1 mt-6 space-y-1">
        <NavLink to="/dashboard" className={navClass}>
          <LayoutDashboard size={20} />
          <span>Inicio</span>
        </NavLink>
        <NavLink to="/requests" className={navClass}>
          <FileText size={20} />
          <span>Solicitudes</span>
        </NavLink>
        <NavLink to="/profile" className={navClass}>
          <User size={20} />
          <span>Mi Perfil</span>
        </NavLink>
      </nav>

      <div className="p-6 border-t border-gray-700/50 bg-black/20">
        <div className="flex items-center space-x-3 mb-4">
          <img 
            src={user?.avatarUrl} 
            alt="Avatar" 
            className="w-10 h-10 rounded-full border-2 border-brand-primary p-0.5"
          />
          <div className="overflow-hidden">
            <p className="text-sm font-medium text-white truncate">{user?.fullName}</p>
            <p className="text-xs text-gray-400 truncate">{user?.role}</p>
          </div>
        </div>
        <button 
          onClick={logout}
          className="flex items-center space-x-2 text-gray-400 hover:text-brand-turmalina transition-colors text-sm w-full group"
        >
          <LogOut size={16} className="group-hover:translate-x-1 transition-transform" />
          <span>Cerrar Sesión</span>
        </button>
      </div>
    </div>
  );
}
