import React, { useState, useEffect } from 'react';
import { Mail, Lock, Building2, User as UserIcon, ArrowRight, Loader2 } from 'lucide-react';
import { Role, User } from '../types';
import { useAuth } from '../App';

// Datos de ejemplo para el autocompletado (Esto vendrá de Supabase después)
const MOCK_COMPANIES = [
  { id: '1', nombre: 'Disruptive Corp' },
  { id: '2', nombre: 'Tech Solutions SA' },
  { id: '3', nombre: 'Innovación Local' },
];

const Login: React.FC = () => {
  const { login: authLogin } = useAuth();
  const [isRegistering, setIsRegistering] = useState(false);
  const [loading, setLoading] = useState(false);
  
  // Estados del Formulario
  const [formData, setFormData] = useState({
    fullName: '',
    empresaNombre: '',
    email: '',
    password: '',
  });

  // Estados para Autocompletado
  const [suggestions, setSuggestions] = useState<{id: string, nombre: string}[]>([]);
  const [showSuggestions, setShowSuggestions] = useState(false);

  // Lógica de Autocompletado
  useEffect(() => {
    if (formData.empresaNombre.length >= 3) {
      const filtered = MOCK_COMPANIES.filter(c => 
        c.nombre.toLowerCase().includes(formData.empresaNombre.toLowerCase())
      );
      setSuggestions(filtered);
      setShowSuggestions(true);
    } else {
      setSuggestions([]);
      setShowSuggestions(false);
    }
  }, [formData.empresaNombre]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    
    // Simulación de delay de red
    setTimeout(() => {
      const mockUser: User = {
        id: 'new-user-123',
        email: formData.email,
        fullName: formData.fullName || 'Usuario Demo',
        role: Role.COLLABORATOR,
      };
      authLogin(mockUser);
      setLoading(false);
    }, 1500);
  };

  const handleLogin = async (e: React.FormEvent) => {
  e.preventDefault();
  try {
    const { data, error } = await supabase.auth.signInWithPassword({
      email: correo,
      password: password,
    });

    if (error) {
      // Si el error es "Invalid login credentials", significa que no existe o la clave es errónea
      if (error.message.includes("Invalid login credentials")) {
        alert("Usuario no registrado. Crea tu cuenta en 'Regístrate aquí'");
      } else {
        alert(error.message);
      }
      return;
    }

    // Si el login es exitoso, actualiza el estado global
    await checkAuth(); 
  } catch (err) {
    console.error("Error inesperado:", err);
  }
};
  
  return (
    <div className="min-h-screen bg-slate-50 flex flex-col justify-center py-12 sm:px-6 lg:px-8">
      <div className="sm:mx-auto sm:w-full sm:max-w-md text-center">
        <img src="icon_light.png" alt="Logo" className="mx-auto h-12 w-auto mb-4" />
        <h2 className="text-3xl font-extrabold text-slate-900">
          {isRegistering ? 'Crea tu cuenta de colaborador' : 'Bienvenido de nuevo'}
        </h2>
        <p className="mt-2 text-sm text-slate-600">
          {isRegistering ? '¿Ya tienes cuenta?' : '¿Eres nuevo colaborador?'}
          <button 
            onClick={() => setIsRegistering(!isRegistering)}
            className="ml-1 font-medium text-blue-600 hover:text-blue-500 transition-colors"
          >
            {isRegistering ? 'Inicia sesión aquí' : 'Regístrate aquí'}
          </button>
        </p>
      </div>

      <div className="mt-8 sm:mx-auto sm:w-full sm:max-w-md">
        <div className="bg-white py-8 px-4 shadow-xl border border-slate-200 sm:rounded-2xl sm:px-10">
          <form className="space-y-6" onSubmit={handleSubmit}>
            
            {isRegistering && (
              <>
                {/* Nombre Completo */}
                <div>
                  <label className="block text-sm font-medium text-slate-700">Nombre Completo</label>
                  <div className="mt-1 relative">
                    <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                      <UserIcon className="h-5 w-5 text-slate-400" />
                    </div>
                    <input
                      type="text"
                      required
                      className="block w-full pl-10 pr-3 py-2 border border-slate-300 rounded-lg focus:ring-blue-500 focus:border-blue-500 text-sm"
                      placeholder="Juan Pérez"
                      value={formData.fullName}
                      onChange={(e) => setFormData({...formData, fullName: e.target.value})}
                    />
                  </div>
                </div>

                {/* Empresa con Autocompletado */}
                <div className="relative">
                  <label className="block text-sm font-medium text-slate-700">Empresa donde laboras</label>
                  <div className="mt-1 relative">
                    <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                      <Building2 className="h-5 w-5 text-slate-400" />
                    </div>
                    <input
                      type="text"
                      required
                      className="block w-full pl-10 pr-3 py-2 border border-slate-300 rounded-lg focus:ring-blue-500 focus:border-blue-500 text-sm"
                      placeholder="Nombre de tu empresa"
                      value={formData.empresaNombre}
                      onChange={(e) => setFormData({...formData, empresaNombre: e.target.value})}
                    />
                  </div>
                  
                  {/* Dropdown de Sugerencias */}
                  {showSuggestions && suggestions.length > 0 && (
                    <ul className="absolute z-10 mt-1 w-full bg-white shadow-lg max-h-40 rounded-md py-1 text-base ring-1 ring-black ring-opacity-5 overflow-auto focus:outline-none sm:text-sm">
                      {suggestions.map((s) => (
                        <li 
                          key={s.id}
                          className="cursor-pointer select-none relative py-2 pl-3 pr-9 hover:bg-blue-50 text-slate-900"
                          onClick={() => {
                            setFormData({...formData, empresaNombre: s.nombre});
                            setShowSuggestions(false);
                          }}
                        >
                          {s.nombre}
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              </>
            )}

            {/* Correo Corporativo */}
            <div>
              <label className="block text-sm font-medium text-slate-700">Correo Corporativo</label>
              <div className="mt-1 relative">
                <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                  <Mail className="h-5 w-5 text-slate-400" />
                </div>
                <input
                  type="email"
                  required
                  className="block w-full pl-10 pr-3 py-2 border border-slate-300 rounded-lg focus:ring-blue-500 focus:border-blue-500 text-sm"
                  placeholder="usuario@empresa.com"
                  value={formData.email}
                  onChange={(e) => setFormData({...formData, email: e.target.value})}
                />
              </div>
            </div>

            {/* Contraseña */}
            <div>
              <label className="block text-sm font-medium text-slate-700">Contraseña</label>
              <div className="mt-1 relative">
                <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                  <Lock className="h-5 w-5 text-slate-400" />
                </div>
                <input
                  type="password"
                  required
                  className="block w-full pl-10 pr-3 py-2 border border-slate-300 rounded-lg focus:ring-blue-500 focus:border-blue-500 text-sm"
                  placeholder="••••••••"
                  value={formData.password}
                  onChange={(e) => setFormData({...formData, password: e.target.value})}
                />
              </div>
            </div>

            {!isRegistering && (
              <div className="flex items-center justify-end">
                <button type="button" className="text-sm font-medium text-blue-600 hover:text-blue-500">
                  ¿Olvidaste tu contraseña?
                </button>
              </div>
            )}

            <div>
              <button
                type="submit"
                disabled={loading}
                className="w-full flex justify-center py-3 px-4 border border-transparent rounded-lg shadow-sm text-sm font-semibold text-white bg-blue-600 hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {loading ? (
                  <Loader2 className="animate-spin h-5 w-5" />
                ) : (
                  <>
                    {isRegistering ? 'Crear cuenta' : 'Entrar al portal'}
                    <ArrowRight className="ml-2 h-5 w-5" />
                  </>
                )}
              </button>
            </div>
          </form>
        </div>
      </div>
    </div>
  );
};

export default Login;
