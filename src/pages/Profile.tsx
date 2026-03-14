import React, { useState } from 'react';
import { User as UserIcon, Briefcase, Calendar, Fingerprint, Mail, Phone, Save, CheckCircle } from 'lucide-react';
import { useAuth } from '../App';

const Profile: React.FC = () => {
  const { user } = useAuth();
  const [isSaving, setIsSaving] = useState(false);
  const [showSuccess, setShowSuccess] = useState(false);

  // Estado local para los campos editables
  const [formData, setFormData] = useState({
    area: user?.area || '',
    tipoIdentificacion: user?.tipoIdentificacion || 'Cédula de Ciudadanía',
    numeroIdentificacion: user?.numeroIdentificacion || '',
    correoPersonal: user?.correoPersonal || '',
    telefonoWhatsapp: user?.telefonoWhatsapp || '',
  });

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsSaving(true);
    // Aquí irá la llamada a Supabase después
    setTimeout(() => {
      setIsSaving(false);
      setShowSuccess(true);
      setTimeout(() => setShowSuccess(false), 3000);
    }, 1000);
  };

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      <div className="md:flex md:items-center md:justify-between">
        <div className="flex-1 min-w-0">
          <h2 className="text-2xl font-bold leading-7 text-slate-900 sm:text-3xl sm:truncate">
            Mi Perfil
          </h2>
          <p className="mt-1 text-sm text-slate-500">
            Gestiona tu información personal y verifica tus datos laborales.
          </p>
        </div>
      </div>

      <form onSubmit={handleSave} className="space-y-6">
        {/* Sección: Información Laboral (Solo Lectura) */}
        <div className="bg-white shadow-sm border border-slate-200 rounded-xl overflow-hidden">
          <div className="px-4 py-5 sm:px-6 bg-slate-50 border-b border-slate-200">
            <h3 className="text-lg leading-6 font-medium text-slate-900 flex items-center">
              <Briefcase className="mr-2 h-5 w-5 text-blue-600" />
              Información Laboral
            </h3>
          </div>
          <div className="px-4 py-5 sm:p-6 grid grid-cols-1 md:grid-cols-2 gap-6">
            <div>
              <label className="block text-sm font-medium text-slate-500">Rol / Puesto</label>
              <div className="mt-1 text-slate-900 font-medium">{user?.rolPuesto || 'No asignado'}</div>
            </div>
            <div>
              <label className="block text-sm font-medium text-slate-500">Área / Departamento</label>
              <div className="mt-1 text-slate-900 font-medium">{user?.area || 'General'}</div>
            </div>
            <div>
              <label className="block text-sm font-medium text-slate-500">Fecha de Ingreso</label>
              <div className="mt-1 flex items-center text-slate-900 font-medium">
                <Calendar className="mr-2 h-4 w-4 text-slate-400" />
                {user?.fechaIngreso || 'Consultar con RH'}
              </div>
            </div>
            <div>
              <label className="block text-sm font-medium text-slate-500">Correo Corporativo</label>
              <div className="mt-1 text-slate-900 font-medium">{user?.email}</div>
            </div>
          </div>
        </div>

        {/* Sección: Datos de Identificación y Contacto (Editable) */}
        <div className="bg-white shadow-sm border border-slate-200 rounded-xl overflow-hidden">
          <div className="px-4 py-5 sm:px-6 bg-slate-50 border-b border-slate-200">
            <h3 className="text-lg leading-6 font-medium text-slate-900 flex items-center">
              <Fingerprint className="mr-2 h-5 w-5 text-blue-600" />
              Datos Personales
            </h3>
          </div>
          <div className="px-4 py-5 sm:p-6 grid grid-cols-1 md:grid-cols-2 gap-6">
            <div>
              <label className="block text-sm font-medium text-slate-700">Tipo de Identificación</label>
              <select
                className="mt-1 block w-full pl-3 pr-10 py-2 text-base border-slate-300 focus:outline-none focus:ring-blue-500 focus:border-blue-500 sm:text-sm rounded-lg"
                value={formData.tipoIdentificacion}
                onChange={(e) => setFormData({...formData, tipoIdentificacion: e.target.value})}
              >
                <option>Cédula de Ciudadanía</option>
                <option>Cédula de Extranjería</option>
                <option>Pasaporte</option>
                <option>NIT (Personal)</option>
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-slate-700">Número de Identificación</label>
              <input
                type="text"
                className="mt-1 block w-full border-slate-300 rounded-lg shadow-sm focus:ring-blue-500 focus:border-blue-500 sm:text-sm"
                value={formData.numeroIdentificacion}
                onChange={(e) => setFormData({...formData, numeroIdentificacion: e.target.value})}
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-slate-700 flex items-center">
                <Mail className="mr-2 h-4 w-4 text-slate-400" />
                Correo Personal
              </label>
              <input
                type="email"
                className="mt-1 block w-full border-slate-300 rounded-lg shadow-sm focus:ring-blue-500 focus:border-blue-500 sm:text-sm"
                placeholder="ejemplo@gmail.com"
                value={formData.correoPersonal}
                onChange={(e) => setFormData({...formData, correoPersonal: e.target.value})}
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-slate-700 flex items-center">
                <Phone className="mr-2 h-4 w-4 text-slate-400" />
                Teléfono móvil / WhatsApp
              </label>
              <input
                type="text"
                className="mt-1 block w-full border-slate-300 rounded-lg shadow-sm focus:ring-blue-500 focus:border-blue-500 sm:text-sm"
                placeholder="+57 300 000 0000"
                value={formData.telefonoWhatsapp}
                onChange={(e) => setFormData({...formData, telefonoWhatsapp: e.target.value})}
              />
            </div>
          </div>
          
          <div className="px-4 py-3 bg-slate-50 text-right sm:px-6 border-t border-slate-200">
            <button
              type="submit"
              disabled={isSaving}
              className="inline-flex justify-center py-2 px-4 border border-transparent shadow-sm text-sm font-medium rounded-md text-white bg-blue-600 hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 disabled:opacity-50"
            >
              {isSaving ? 'Guardando...' : (
                <>
                  <Save className="mr-2 h-4 w-4" />
                  Actualizar Perfil
                </>
              )}
            </button>
          </div>
        </div>
      </form>

      {showSuccess && (
        <div className="fixed bottom-4 right-4 bg-green-50 border border-green-200 text-green-800 px-4 py-3 rounded-lg shadow-lg flex items-center animate-bounce">
          <CheckCircle className="mr-2 h-5 w-5 text-green-500" />
          Perfil actualizado correctamente
        </div>
      )}
    </div>
  );
};

export default Profile;
