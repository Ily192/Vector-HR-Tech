import React, { useState, useEffect } from 'react';
import { useAuth } from '../App';
import { dataService } from '../services/dataService';
import { Request, RequestType, RequestStatus } from '../types';
import { FilePlus, History, Send, Loader2, CheckCircle, XCircle, Clock } from 'lucide-react';

export default function Requests() {
  const { user } = useAuth();
  const [requests, setRequests] = useState<Request[]>([]);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);

  // Form State
  const [requestType, setRequestType] = useState<RequestType>(RequestType.TIME_OFF);
  const [details, setDetails] = useState('');

  useEffect(() => {
    loadRequests();
  }, []);

  const loadRequests = async () => {
    setLoading(true);
    const data = await dataService.getRequests();
    setRequests(data);
    setLoading(false);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    try {
      await dataService.createRequest(requestType, details);
      setDetails('');
      loadRequests(); // Reload list
      alert("Solicitud enviada con éxito");
    } catch (error) {
      alert("Error al enviar solicitud");
    } finally {
      setSubmitting(false);
    }
  };

  const getStatusIcon = (status: RequestStatus) => {
    switch (status) {
      case RequestStatus.APPROVED: return <CheckCircle className="text-brand-jade" size={18} />;
      case RequestStatus.REJECTED: return <XCircle className="text-red-500" size={18} />;
      default: return <Clock className="text-yellow-500" size={18} />;
    }
  };

  return (
    <div className="space-y-6 max-w-5xl mx-auto font-sans">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-brand-secondary">Solicitudes RRHH</h1>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        {/* Form Section */}
        <div className="lg:col-span-1">
          <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-6 sticky top-8">
            <h2 className="text-lg font-semibold text-brand-secondary mb-4 flex items-center gap-2">
              <FilePlus className="text-brand-primary" size={20} />
              Nueva Solicitud
            </h2>
            <form onSubmit={handleSubmit} className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Tipo de Solicitud</label>
                <select
                  value={requestType}
                  onChange={(e) => setRequestType(e.target.value as RequestType)}
                  className="w-full border border-gray-300 rounded-lg p-2.5 focus:ring-2 focus:ring-brand-primary outline-none bg-white transition-all"
                >
                  {Object.values(RequestType).map((t) => (
                    <option key={t} value={t}>{t}</option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Detalles / Justificación</label>
                <textarea
                  required
                  value={details}
                  onChange={(e) => setDetails(e.target.value)}
                  className="w-full border border-gray-300 rounded-lg p-3 focus:ring-2 focus:ring-brand-primary outline-none h-32 resize-none transition-all"
                  placeholder="Describe brevemente el motivo..."
                />
              </div>

              <button
                type="submit"
                disabled={submitting}
                className="w-full bg-brand-primary hover:bg-cyan-500 text-white font-medium py-2.5 px-4 rounded-lg transition-colors flex items-center justify-center space-x-2 disabled:opacity-50 shadow-md shadow-brand-primary/20"
              >
                {submitting ? <Loader2 className="animate-spin" size={20}/> : <><Send size={18} /> <span>Enviar Solicitud</span></>}
              </button>
            </form>
          </div>
        </div>

        {/* History Section */}
        <div className="lg:col-span-2">
          <div className="bg-white rounded-xl shadow-sm border border-gray-100 overflow-hidden">
            <div className="p-6 border-b border-gray-100">
              <h2 className="text-lg font-semibold text-brand-secondary flex items-center gap-2">
                <History className="text-gray-400" size={20} />
                Historial de Solicitudes
              </h2>
            </div>
            
            {loading ? (
              <div className="p-8 text-center text-gray-500">Cargando...</div>
            ) : requests.length === 0 ? (
              <div className="p-8 text-center text-gray-500">No hay solicitudes recientes.</div>
            ) : (
              <div className="divide-y divide-gray-100">
                {requests.map((req) => (
                  <div key={req.id} className="p-4 hover:bg-gray-50 transition-colors">
                    <div className="flex items-start justify-between">
                      <div>
                        <span className="text-sm font-bold text-brand-secondary block mb-1">{req.type}</span>
                        <p className="text-gray-600 text-sm mb-2">{req.details}</p>
                        <p className="text-xs text-gray-400">{new Date(req.date).toLocaleDateString()}</p>
                      </div>
                      <div className="flex items-center gap-1.5 px-3 py-1 rounded-full bg-gray-50 border border-gray-100">
                        {getStatusIcon(req.status)}
                        <span className={`text-xs font-semibold ${
                          req.status === RequestStatus.APPROVED ? 'text-brand-secondary' :
                          req.status === RequestStatus.REJECTED ? 'text-red-600' :
                          'text-yellow-600'
                        }`}>
                          {req.status}
                        </span>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
