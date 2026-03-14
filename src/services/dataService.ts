import { supabase } from './supabaseClient';
import { User, Role, Empresa } from '../types';

export const dataService = {
  // 1. Obtener perfil actual
  getCurrentProfile: async (): Promise<{ user: User | null, needsProfile: boolean }> => {
    const { data: { session } } = await supabase.auth.getSession();
    if (!session) return { user: null, needsProfile: false };

    const { data: profile, error } = await supabase
      .from('profiles')
      .select('*')
      .eq('id', session.user.id)
      .single();

    if (error || !profile) {
      // Si hay sesión pero no hay fila en 'profiles', toca completar registro
      return { user: null, needsProfile: true };
    }

    return { 
      user: {
        id: profile.id,
        email: profile.email,
        fullName: profile.full_name, // Mapeo de BD a Frontend
        role: profile.role as Role,
        empresaId: profile.empresa_id,
        area: profile.area,
        rolPuesto: profile.rol_puesto
      }, 
      needsProfile: false 
    };
  },

  // 2. Buscar empresas para el autocompletado
  searchCompanies: async (query: string): Promise<Empresa[]> => {
    const { data, error } = await supabase
      .from('empresas')
      .select('*')
      .ilike('nombre', `%${query}%`)
      .limit(5);

    if (error) return [];
    return data.map(emp => ({
      id: emp.id,
      nombre: emp.nombre,
      nitIdentificacion: emp.nit_identificacion,
      logoUrl: emp.logo_url
    }));
  },

  // 3. Guardar el perfil inicial (CORREGIDO PARA TU TABLA)
  completeRegistration: async (userData: any) => {
    const { data: { user: authUser } } = await supabase.auth.getUser();
    if (!authUser) throw new Error("No hay sesión activa");

    const { error } = await supabase
      .from('profiles')
      .insert([{
        id: authUser.id,
        email: authUser.email,
        full_name: userData.fullName,    // Nombre en la tabla: full_name
        empresa_id: userData.empresaId,  // Nombre en la tabla: empresa_id
        rol_puesto: userData.rolPuesto,  // Nombre en la tabla: rol_puesto
        area: userData.area              // Nombre en la tabla: area
      }]);

    if (error) throw error;
  }
};
