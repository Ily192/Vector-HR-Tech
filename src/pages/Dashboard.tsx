import React, { useEffect, useState } from 'react';
import { useAuth } from '../App';
import { dataService } from '../services/dataService';
import { getEmotionalFeedback } from '../services/geminiService';
import { Project, Mood } from '../types';
import { Briefcase, Calendar, Clock, Smile, Frown, Meh, Sparkles, Loader2 } from 'lucide-react';
import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip as RechartsTooltip, Legend } from 'recharts';
import { formatDistanceToNow, parseISO } from 'date-fns';
import { es } from 'date-fns/locale';

export default function Dashboard() {
  const { user } = useAuth();
  const [projects, setProjects] = useState<Project[]>([]);
  const [selectedMood, setSelectedMood] = useState<Mood | null>(null);
  const [aiFeedback, setAiFeedback] = useState<string>('');
  const [loadingFeedback, setLoadingFeedback] = useState(false);

  useEffect(() => {
    const loadData = async () => {
      const projs = await dataService.getProjects();
      setProjects(projs);
    };
    loadData();
  }, []);

  const handleMoodSelect = async (mood: Mood) => {
    setSelectedMood(mood);
    setLoadingFeedback(true);
    setAiFeedback('');
    
    // Call Gemini API
    const feedback = await getEmotionalFeedback(mood, user?.fullName || 'Colaborador');
    setAiFeedback(feedback);
    setLoadingFeedback(false);
  };

  if (!user) return null;

  const tenure = formatDistanceToNow(parseISO(user.startDate), { locale: es });
  
  // Brand Colors for Charts
  const ptoData = [
    { name: 'Disfrutados', value: user.ptoTaken, color: '#37b1d3' }, // Topacio (Brand Primary)
    { name: 'Disponibles', value: user.ptoTotal - user.ptoTaken, color: '#262f3f' }, // Onix (Brand Secondary)
  ];

  return (
    <div className="space-y-6 animate-fade-in font-sans">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-brand-secondary">Hola, {user.fullName.split(' ')[0]} 👋</h1>
          <p className="text-gray-500">Aquí tienes el resumen de tu actividad y beneficios.</p>
        </div>
        <div className="bg-white px-4 py-2 rounded-full shadow-sm border border-gray-200 flex items-center space-x-2 text-sm text-gray-600">
          <Clock size={16} className="text-brand-primary" />
          <span>Tiempo en la empresa: <strong>{tenure}</strong></span>
        </div>
      </div>

      {/* Emotional Salary Check-in */}
      <div className="bg-gradient-to-r from-brand-secondary to-brand-zafiro rounded-2xl p-6 text-white shadow-xl relative overflow-hidden">
        {/* Decorative elements */}
        <div className="absolute right-0 top-0 w-32 h-32 bg-brand-primary opacity-20 rounded-full blur-2xl"></div>
        <div className="absolute left-10 bottom-0 w-24 h-24 bg-brand-turmalina opacity-20 rounded-full blur-2xl"></div>

        <div className="relative z-10 flex flex-col md:flex-row items-start md:items-center justify-between gap-6">
          <div className="max-w-lg">
            <h2 className="text-lg font-semibold flex items-center gap-2">
              <Sparkles className="text-brand-jade" /> 
              Check-in Emocional
            </h2>
            <p className="text-gray-200 text-sm mt-1 mb-4">
              ¿Cómo inicias tu jornada hoy? Tu bienestar es nuestra prioridad.
            </p>
            
            {!selectedMood ? (
              <div className="flex gap-4">
                {[
                  { mood: Mood.HAPPY, icon: Smile, color: 'hover:text-brand-jade' },
                  { mood: Mood.NEUTRAL, icon: Meh, color: 'hover:text-brand-primary' },
                  { mood: Mood.STRESSED, icon: Frown, color: 'hover:text-brand-turmalina' },
                ].map(({ mood, icon: Icon, color }) => (
                  <button
                    key={mood}
                    onClick={() => handleMoodSelect(mood)}
                    className={`p-2 bg-white/10 rounded-full backdrop-blur-sm transition-all hover:scale-110 hover:bg-white/20 ${color}`}
                  >
                    <Icon size={32} />
                  </button>
                ))}
              </div>
            ) : (
              <div className="bg-white/10 rounded-lg p-4 backdrop-blur-sm border border-white/20">
                 {loadingFeedback ? (
                   <div className="flex items-center gap-2">
                     <Loader2 className="animate-spin text-brand-primary" size={18} />
                     <span className="text-sm">Generando consejo de bienestar con IA...</span>
                   </div>
                 ) : (
                   <p className="text-sm font-medium italic">"{aiFeedback}"</p>
                 )}
              </div>
            )}
          </div>
          
          {/* Skills Badges */}
          <div className="bg-black/20 p-4 rounded-xl backdrop-blur-md border border-white/5 w-full md:w-auto">
            <h3 className="text-xs font-semibold uppercase tracking-wider text-brand-primary mb-2">Habilidades Destacadas</h3>
            <div className="flex flex-wrap gap-2">
              {user.skills.map(skill => (
                <span key={skill} className="text-xs bg-brand-primary/20 text-brand-primary px-2 py-1 rounded border border-brand-primary/30">
                  {skill}
                </span>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* Main Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        
        {/* PTO Card */}
        <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-6">
          <h3 className="text-lg font-semibold text-brand-secondary mb-4 flex items-center gap-2">
            <Calendar className="text-brand-primary" size={20} />
            Días Libres
          </h3>
          <div className="h-48 relative">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie
                  data={ptoData}
                  cx="50%"
                  cy="50%"
                  innerRadius={60}
                  outerRadius={80}
                  paddingAngle={5}
                  dataKey="value"
                >
                  {ptoData.map((entry, index) => (
                    <Cell key={`cell-${index}`} fill={entry.color} />
                  ))}
                </Pie>
                <RechartsTooltip />
                <Legend verticalAlign="bottom" height={36}/>
              </PieChart>
            </ResponsiveContainer>
            <div className="absolute top-1/2 left-1/2 transform -translate-x-1/2 -translate-y-1/2 text-center pb-8">
              <span className="text-3xl font-bold text-brand-secondary">{user.ptoTotal - user.ptoTaken}</span>
              <p className="text-xs text-gray-400">Restantes</p>
            </div>
          </div>
        </div>

        {/* Projects Card */}
        <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-6 lg:col-span-2">
          <h3 className="text-lg font-semibold text-brand-secondary mb-4 flex items-center gap-2">
            <Briefcase className="text-brand-primary" size={20} />
            Proyectos Activos
          </h3>
          <div className="space-y-4">
            {projects.map(project => (
              <div key={project.id} className="flex items-center justify-between p-4 bg-gray-50 rounded-lg border border-gray-100 hover:border-brand-primary/30 transition-colors group">
                <div>
                  <h4 className="font-medium text-brand-secondary group-hover:text-brand-primary transition-colors">{project.name}</h4>
                  <p className="text-sm text-gray-500">{project.role}</p>
                </div>
                <span className={`px-3 py-1 rounded-full text-xs font-medium ${
                  project.status === 'Active' ? 'bg-brand-jade/10 text-brand-secondary border border-brand-jade/30' :
                  project.status === 'Completed' ? 'bg-gray-100 text-gray-700' :
                  'bg-yellow-100 text-yellow-700'
                }`}>
                  {project.status === 'Active' ? 'Activo' : project.status}
                </span>
              </div>
            ))}
            {projects.length === 0 && (
              <p className="text-gray-500 text-sm">No tienes proyectos asignados actualmente.</p>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
