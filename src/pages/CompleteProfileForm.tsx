import React, { useState, useEffect } from 'react';
import { dataService } from '../services/dataService';
import { useAuth } from '../App';
import { Empresa } from '../types';

const CompleteProfileForm = () => {
  const { checkAuth } = useAuth();
  const [formData, setFormData] = useState({ fullName: '', empresaId: '', rolPuesto: '', area: '' });
  const [empresaSearch, setEmpresaSearch] = useState('');
  const [empresasSugeridas, setEmpresasSugeridas] = useState<Empresa[]>([]);

  useEffect(() => {
    const delayDebounce = setTimeout(async () => {
      if (empresaSearch.length >= 3) {
        const res = await dataService.searchCompanies(empresaSearch);
        setEmpresasSugeridas(res);
      }
    }, 300);
    return () => clearTimeout(delayDebounce);
  }, [empresaSearch]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!formData.empresaId) return alert("Selecciona una empresa de la lista");

    try {
      await dataService.completeRegistration(formData);
      await checkAuth(); // Esto recargará App.tsx y te llevará al Dashboard
    } catch (err) {
      alert("Error al guardar. Revisa la consola.");
      console.error(err);
    }
  };

  return (
    <div className="min-h-screen bg-gray-100 flex items-center justify-center p-4">
      <form onSubmit={handleSubmit} className="max-w-md w-full bg-white p-8 rounded-2xl shadow-lg space-y-4">
        <h2 className="text-xl font-bold text-center">Finaliza tu Perfil</h2>
        
        <input className="w-full p-2 border rounded" placeholder="Nombre Completo" required
          onChange={e => setFormData({...formData, fullName: e.target.value})} />
        
        <div className="relative">
          <input className="w-full p-2 border rounded" placeholder="Buscar Empresa..." value={empresaSearch}
            onChange={e => setEmpresaSearch(e.target.value)} />
          {empresaSearch.length >= 3 && empresasSugeridas.length > 0 && (
            <ul className="absolute z-10 w-full bg-white border shadow-md">
              {empresasSugeridas.map(emp => (
                <li key={emp.id} className="p-2 hover:bg-gray-100 cursor-pointer" 
                    onClick={() => { setFormData({...formData, empresaId: emp.id}); setEmpresaSearch(emp.nombre); setEmpresasSugeridas([]); }}>
                  {emp.nombre}
                </li>
              ))}
            </ul>
          )}
        </div>

        <input className="w-full p-2 border rounded" placeholder="Área" required
          onChange={e => setFormData({...formData, area: e.target.value})} />
        
        <input className="w-full p-2 border rounded" placeholder="Puesto" required
          onChange={e => setFormData({...formData, rolPuesto: e.target.value})} />

        <button type="submit" className="w-full bg-blue-600 text-white py-2 rounded font-bold hover:bg-blue-700">
          Guardar y Entrar
        </button>
      </form>
    </div>
  );
};

export default CompleteProfileForm;
